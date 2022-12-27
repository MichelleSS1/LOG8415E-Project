import json
import os
import sys
from time import sleep, time
import boto3
import paramiko
from infra_utils import InfraInfo, create_security_group, authorize_ingress, filters_from_tags, get_key_pair_name, get_subnets, get_vpc_id, save_infra_info
from instance import create_ubuntu_instances, get_instances_ids, stopped_instances_ids

ec2_client = boto3.client('ec2')
ec2 = boto3.resource('ec2')

SSH_PORT = 22
MYSQL_PORT = 3306
NDB_MANAGER_PORT = 1186
NDB_DATA_NODE_PORT = 2202
FLASK_PORT = 5000
TINYPROXY_PORT = 8888


def get_absolute_path(relative_path: str):
    return os.path.join(sys.path[0], relative_path)

def ssh_connect_with_retries(client: paramiko.SSHClient, hostname: str, key_filename: str, wait_time: int):
    """
    Retry an SSH connection till connected or wait_time is elapsed.

    @param client: paramiko.SSHClient       Paramiko SSHClient to use for connection
    @param hostname: str                    Hostname to connect to
    @param key_filename: str                The name of the file holding the private key
    @param wait_time: int                   Time interval during which it's possible to retry
    """

    connected = False
    start = time()
    while not connected and (time() - start < wait_time):
        try:
            client.connect(hostname=hostname, port=22,
                        username='ubuntu', key_filename=key_filename)
        except:
            pass
        else:
            connected = True

            print("connected", time() - start)

    if not connected:
        raise Exception(f"Couldn't establish an SSH connection to host {hostname}")

def get_jumpbox_ssh_public_key(jumpbox_dns_name: str):
    """
    Create and copy jumpbox SSH key pair.

    @param jumpbox_dns_name: str            Jumpbox public dns name

    @return: str                            Jumpbox SSH public key
    """

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

    pKey_filename = get_absolute_path('../pkey.pem')

    print("SSH connection to jumpbox")
    ssh_connect_with_retries(client, jumpbox_dns_name, pKey_filename, 120)

    with open(get_absolute_path('scripts/gen_jumpbox_ssh_keypair.sh')) as f:
        script = f.read()

    print("Copying jumpbox SSH public key")
    _, stdout, stderr = client.exec_command(command=script, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        for line in stderr.readlines():
            print(line)
        raise Exception("Failed to copy key")

    jumpbox_pub_key = stdout.read().decode('ascii').strip("\n")

    print("done\n")

    return jumpbox_pub_key


def create_jumpbox(vpc_id: str, subnet_id: str, key_name: str, tags: dict[str, str]):
    """
    Create jumpbox instance with its security group and SSH key pair.

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance, str              Jumpbox EC2 instance and SSH public key
    """

    print("Jumpbox creation")

    sec_group_jumpbox = create_security_group(
        "sec_group_jumpbox", "Security group for Jumpbox", vpc_id, tags)
    authorize_ingress(sec_group_jumpbox, [
        {"protocol": "tcp", "port": SSH_PORT, "ip_range": "0.0.0.0/0"}
    ])

    jumpbox_instance = create_ubuntu_instances("t2.micro", 1, 1, key_name, True, subnet_id,
                                               [sec_group_jumpbox.id], tags | {"Name": "Jumpbox"}, '')[0]

    print("Waiting for jumpbox to be running")
    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(InstanceIds=[jumpbox_instance.id])
    jumpbox_instance.reload()
    sleep(30)
    print("done\n")

    jumpbox_pub_key = get_jumpbox_ssh_public_key(
        jumpbox_instance.public_dns_name)

    print("done\n")

    return jumpbox_instance, jumpbox_pub_key

def create_standalone_mysql(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, tags: dict[str, str]):
    """
    Create standalone mysql server instance with its security group.

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance                   Standalone mysql server EC2 instance
    """

    print("Standalone mysql creation")

    sec_group_standalone_mysql = create_security_group(
        "sec_group_standalone_mysql", "Security group for Standalone MySQL", vpc_id, tags)
    authorize_ingress(sec_group_standalone_mysql, [
        {"protocol": "tcp", "port": MYSQL_PORT, "ip_range": "0.0.0.0/0"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    standalone_mysql_instance = create_ubuntu_instances(
        "t2.micro", 1, 1, key_name, True, subnet_id, [sec_group_standalone_mysql.id], tags | {"Name": "Standalone"}, user_data)[0]

    print("done\n")
    return standalone_mysql_instance

def create_gatekeeper(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, tags: dict[str, str]):
    """
    Create Gatekeeper instance with its security group.

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance                   Gatekeeper EC2 instance
    """

    print("Gatekeeper creation")

    sec_group_gatekeeper = create_security_group(
        "sec_group_gatekeeper", "Security group for Gatekeeper node", vpc_id, tags)
    authorize_ingress(sec_group_gatekeeper, [
        {"protocol": "tcp", "port": FLASK_PORT, "ip_range": "0.0.0.0/0"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    gatekeeper_instance = create_ubuntu_instances(
        "t2.large", 1, 1, key_name, True, subnet_id, [sec_group_gatekeeper.id], tags | {"Name": "Gatekeeper"}, user_data)[0]

    print("done\n")
    return gatekeeper_instance

def create_proxy(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, gatekeeper_private_ip: str, tags: dict[str, str]):
    """
    Create Proxy instance (for proxy pattern) with its security group. This instance also plays 
    the role of the trusted host in the gatekeeper pattern.

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param gatekeeper_private_ip: str       Gatekeeper private IP to allow flask server access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance                   Proxy EC2 instance
    """

    print("Proxy creation")

    sec_group_proxy = create_security_group(
        "sec_group_proxy", "Security group for Proxy node", vpc_id, tags)
    authorize_ingress(sec_group_proxy, [
        {"protocol": "tcp", "port": FLASK_PORT,
            "ip_range": gatekeeper_private_ip + "/32"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    proxy_instance = create_ubuntu_instances("t2.large", 1, 1, key_name, False, subnet_id,
                                             [sec_group_proxy.id], tags | {"Name": "Proxy"}, user_data)[0]

    print("done\n")
    return proxy_instance

def create_manager(vpc_id: str, subnet_id: str, subnet_cidr: str, key_name: str, user_data: str, jumpbox_private_ip: str, proxy_private_ip: str, tags: dict[str, str]):
    """
    Create NDB cluster Management server instance with its security group. 

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param subnet_cidr: str                 Subnet IP range to restrict cluster connection
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param proxy_private_ip: str            Gatekeeper private IP to allow mysql access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance                   Manager instance
    """

    print("Manager creation")

    sec_group_manager = create_security_group(
        "sec_group_manager", "Security group for Manager node", vpc_id, tags)
    authorize_ingress(sec_group_manager, [
        {"protocol": "tcp", "port": MYSQL_PORT,
            "ip_range": proxy_private_ip + "/32"},
        {"protocol": "tcp", "port": NDB_MANAGER_PORT, "ip_range": subnet_cidr},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    manager_instance = create_ubuntu_instances(
        "t2.small", 1, 1, key_name, False, subnet_id, [sec_group_manager.id], tags | {"Name": "Manager"}, user_data)[0]

    print("done\n")
    return manager_instance

def create_data_nodes(vpc_id: str, subnet_id: str, subnet_cidr: str, key_name: str, user_data: str, jumpbox_private_ip: str, proxy_private_ip: str, tags: dict[str, str]):
    """
    Create NDB cluster data nodes instances with their security group. 

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param subnet_cidr: str                 Subnet IP range to restrict cluster connection
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param proxy_private_ip: str            Gatekeeper private IP to allow mysql server access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: list[ec2.Instance]             Data nodes instances
    """

    print("Data nodes creation")

    sec_group_data_node = create_security_group(
        "sec_group_data_node", "Security group for Data nodes", vpc_id, tags)
    authorize_ingress(sec_group_data_node, [
        {"protocol": "tcp", "port": MYSQL_PORT,
            "ip_range": proxy_private_ip + "/32"},
        {"protocol": "tcp", "port": NDB_DATA_NODE_PORT, "ip_range": subnet_cidr},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    data_nodes_instances = create_ubuntu_instances(
        "t2.small", 3, 3, key_name, False, subnet_id, [sec_group_data_node.id], tags | {"Name": "Data Node"}, user_data)

    print("done\n")
    return data_nodes_instances

def create_tinyproxy(vpc_id: str, subnet_id: str, subnet_cidr: str, key_name: str, user_data: str, jumpbox_private_ip: str, tags: dict[str, str]):
    """
    Create Tinyproxy instance with its security group. 

    @param vpc_id: str                      Virtual Private Cloud ID where to get/create subnets
    @param subnet_id: str                   Subnet where the machines will be located
    @param subnet_cidr: str                 Subnet IP range to restrict access
    @param key_name: str                    The name of the key pair used to connect to the instances
    @param user_data: str                   Script to be executed on startup
    @param jumpbox_private_ip: str          Jumpbox private IP to allow SSH access only to it
    @param tags: dict[str, str]             Tags to put on instances

    @return: ec2.Instance                   Tinyproxy instance
    """
    print("Tinyproxy creation")

    sec_group_tinyproxy = create_security_group(
        "sec_group_tinyproxy", "Security group for Tinyproxy node", vpc_id, tags)
    authorize_ingress(sec_group_tinyproxy, [
        {"protocol": "tcp", "port": TINYPROXY_PORT, "ip_range": subnet_cidr},
        {"protocol": "tcp", "port": SSH_PORT, "ip_range": jumpbox_private_ip + "/32"}
    ])

    with open(get_absolute_path('scripts/setup_tinyproxy.sh'), 'r') as f:
        tinyproxy_user_data = f.read()
        tinyproxy_user_data = tinyproxy_user_data.replace("$port", str(TINYPROXY_PORT))
        tinyproxy_user_data = tinyproxy_user_data.replace("$cidr", subnet_cidr)

    tinyproxy_user_data = tinyproxy_user_data + '\n' + user_data

    tinyproxy_instance = create_ubuntu_instances(
        "t2.micro", 1, 1, key_name, True, subnet_id, [sec_group_tinyproxy.id], tags | {"Name": "Tinyproxy"}, tinyproxy_user_data)[0]

    print("done\n")
    return tinyproxy_instance

def create_instances(infra_info: InfraInfo):
    """
    Create instances composing the infrastructure.

    @param infra_info: InfraInfo                Object that will hold infrastructure information

    @return InfraInfo, dict[str, str]           Object containing infrastructure information, dict of instances IP and dns
    """
    vpc_id = get_vpc_id()

    subnets = get_subnets(vpc_id)
    subnet_id = subnets[0]['SubnetId']
    subnet_cidr = subnets[0]['CidrBlock']

    key_name = get_key_pair_name()

    infra_info.tags = {"Purpose": "LOG8415E-Project"}

    jumpbox_instance, jumpbox_pub_key = create_jumpbox(vpc_id, subnet_id, key_name, infra_info.tags)
    jumpbox_private_ip = jumpbox_instance.private_ip_address

    tinyproxy_instance = create_tinyproxy(vpc_id, subnet_id, subnet_cidr, key_name, 
        f'echo "{jumpbox_pub_key}" >> /home/ubuntu/.ssh/authorized_keys', 
        jumpbox_private_ip, infra_info.tags
    )
    tinyproxy_private_ip = tinyproxy_instance.private_ip_address

    user_data = f'''#!/bin/bash\necho "http_proxy=http://{tinyproxy_private_ip}:{TINYPROXY_PORT}/" >> /etc/environment\necho "https_proxy=http://{tinyproxy_private_ip}:{TINYPROXY_PORT}/" >> /etc/environment\necho "{jumpbox_pub_key}" >> /home/ubuntu/.ssh/authorized_keys'''

    standalone_mysql_instance  = create_standalone_mysql(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, infra_info.tags)

    gatekeeper_instance = create_gatekeeper(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, infra_info.tags)
    gatekeeper_private_ip = gatekeeper_instance.private_ip_address

    proxy_instance = create_proxy(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, gatekeeper_private_ip, infra_info.tags)
    proxy_private_ip = proxy_instance.private_ip_address

    manager_instance = create_manager(vpc_id, subnet_id, subnet_cidr, key_name, user_data, jumpbox_private_ip, proxy_private_ip, infra_info.tags)
    data_nodes_instances = create_data_nodes(vpc_id, subnet_id, subnet_cidr, key_name, user_data, jumpbox_private_ip, proxy_private_ip, infra_info.tags)

    print("Waiting for instances to be in a running state")

    filters = filters_from_tags(infra_info.tags)
    instances_ids = get_instances_ids(filters)
    instances_ids_to_wait = [id for id in instances_ids if id not in stopped_instances_ids(instances_ids)]

    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(InstanceIds=instances_ids_to_wait)
    # For SSH
    sleep(60)

    print("done\n")

    instances_hostnames = {
        "jumpbox": {"host": jumpbox_private_ip, "dns": jumpbox_instance.public_dns_name},
        "tinyproxy": {"host": tinyproxy_private_ip},
        "standalone_mysql": {"host": standalone_mysql_instance.private_ip_address, "dns": standalone_mysql_instance.public_dns_name},
        "gatekeeper": {"host": gatekeeper_private_ip, "dns": gatekeeper_instance.public_dns_name},
        "proxy":  {"host": proxy_private_ip},
        "manager":  {"host": manager_instance.private_ip_address},
        "data_nodes": [{"host": instance.private_ip_address} for instance in data_nodes_instances]
    }

    return infra_info, instances_hostnames


def setup_instances(instances_hostnames: dict):
    print("Setup of instances will start")

    standalone_mysql_host = instances_hostnames["standalone_mysql"]["host"]
    gatekeeper_host = instances_hostnames["gatekeeper"]["host"]
    proxy_host = instances_hostnames["proxy"]["host"]
    manager_host = instances_hostnames["manager"]["host"]
    data_nodes_host = [instances_hostnames["data_nodes"][i]["host"]
                       for i in range(len(instances_hostnames["data_nodes"]))]

    scripts_path = [
        (standalone_mysql_host, get_absolute_path(
            'scripts/setup_standalone_mysql.sh')),
        (gatekeeper_host, get_absolute_path('scripts/setup_gatekeeper.sh')),
        (proxy_host, get_absolute_path('scripts/setup_proxy.sh')),
        (manager_host, get_absolute_path('scripts/setup_ndb_cluster_manager.sh'))
    ]
    scripts_path.extend([
        (data_nodes_host[i], get_absolute_path(
            'scripts/setup_ndb_cluster_data_node.sh'))
        for i in range(len(data_nodes_host))
    ])

    pKey_filename = get_absolute_path('../pkey.pem')

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

    print("SSH connection to jumpbox")
    client.connect(hostname=instances_hostnames["jumpbox"]["dns"],
                   port=22, username='ubuntu', key_filename=pKey_filename)

    all_stderr = []

    jumpbox_script = ''
    with open(get_absolute_path('scripts/jumpbox_ssh_helper.sh'), 'r') as f:
        jumpbox_script = f.read()

    for host, path in scripts_path:

        with open(path, 'r') as f:
            script = f.read()

            script = script.replace(
                "$root_password", os.getenv("ROOT_PASSWORD"))
            script = script.replace("$username", os.getenv("USER"))
            script = script.replace("$user_password", os.getenv("PASSWORD"))

            script = script.replace(
                "$standalone_mysql_host", standalone_mysql_host)
            script = script.replace("$gatekeeper_host", gatekeeper_host)
            script = script.replace("$proxy_host", proxy_host)
            script = script.replace("$manager_host", manager_host)
            script = script.replace(
                "$data_nodes_host", ','.join(data_nodes_host))
            for i in range(len(data_nodes_host)):
                script = script.replace(f"$data_node{i+1}_host", data_nodes_host[i])


        script = jumpbox_script.replace('$host', host).replace('$script', script)

        print(f"Executing setup script of host {host}. It may take some time.")
        _, stdout, stderr = client.exec_command(command=script, get_pty=True)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            all_stderr.append(stderr)
            print("done\n")
        else:
            for line in stderr.readlines():
                print(line)
            raise Exception(f"Failed to setup host {host}")

    stderr_lines = []
    for stderr in all_stderr:
        stderr_lines.extend(stderr.readlines())

    return stderr_lines


if __name__ == '__main__':

    # Necessary information to teardown infra
    infra_info = InfraInfo(
        tags={},
    )

    infra_info.tags = {"Purpose": "LOG8415E-Project"}

    try:
        _, instances_hostnames = create_instances(infra_info)
        with open(get_absolute_path('instances_hostnames.json'), 'w') as f:
            json.dump(instances_hostnames, f)
        stderr = setup_instances(instances_hostnames)
        print("Error output:\n")
        for line in stderr:
            print(line)
    except:
        raise
    finally:
        # Save it to a file for later use
        save_infra_info(infra_info, get_absolute_path('infra_info'))

    print("Infrastructure setup complete")
