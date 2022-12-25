import json
import os
import sys
from time import sleep
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


def get_absolute_path(relative_path: str):
    return os.path.join(sys.path[0], relative_path)

def get_jumpbox_ssh_public_key(jumpbox_dns_name: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

    pKey_filename = get_absolute_path('../pkey.pem')

    print("SSH connection to jumpbox")
    client.connect(hostname=jumpbox_dns_name, port=22,
                   username='ubuntu', key_filename=pKey_filename)

    print("Copying jumpbox SSH public key")
    _, stdout, stderr = client.exec_command(
        command="cat ~/.ssh/id_rsa.pub", get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        for line in stderr:
            print(line)
        raise Exception("Tests execution didn't succeed")

    jumpbox_pub_key = str(stdout.read())

    print("done\n")

    return jumpbox_pub_key


def create_jumpbox(vpc_id: str, subnet_id: str, key_name: str, infra_info: InfraInfo):
    sec_group_jumpbox = create_security_group(
        "sec_group_jumpbox", "Security group for Jumpbox", vpc_id)
    infra_info.security_groups_ids.append(sec_group_jumpbox.id)

    jumpbox_user_data = ''
    with open(get_absolute_path('scripts/gen_jumpbox_ssh_keypair.sh')) as f:
        jumpbox_user_data = f.read()

    jumpbox_instance = create_ubuntu_instances("t2.micro", 1, 1, key_name, True, subnet_id,
                                               sec_group_jumpbox, infra_info.instances_tags | {"Name": "Jumpbox"}, jumpbox_user_data)[0]
    jumpbox_pub_key = get_jumpbox_ssh_public_key(
        jumpbox_instance.public_dns_name)

    authorize_ingress(sec_group_jumpbox, [
        {"protocol": "tcp", "port": SSH_PORT, "ip_range": "0.0.0.0/0"}
    ])

    return jumpbox_instance, jumpbox_pub_key

def create_standalone_mysql(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, infra_info: InfraInfo):
    sec_group_standalone_mysql = create_security_group(
        "sec_group_standalone_mysql", "Security group for Standalone MySQL", vpc_id)
    infra_info.security_groups_ids.append(sec_group_standalone_mysql.id)

    standalone_mysql_instance = create_ubuntu_instances(
        "t2.micro", 1, 1, key_name, True, subnet_id, sec_group_standalone_mysql, infra_info.instances_tags | {"Name": "Standalone"}, user_data)[0]

    authorize_ingress(sec_group_standalone_mysql, [
        {"protocol": "tcp", "port": MYSQL_PORT, "ip_range": "0.0.0.0/0"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    return standalone_mysql_instance

def create_gatekeeper(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, infra_info: InfraInfo):
    sec_group_gatekeeper = create_security_group(
        "sec_group_gatekeeper", "Security group for Gatekeeper node", vpc_id)
    infra_info.security_groups_ids.append(sec_group_gatekeeper.id)

    gatekeeper_instance = create_ubuntu_instances(
        "t2.large", 1, 1, key_name, True, subnet_id, sec_group_gatekeeper, infra_info.instances_tags | {"Name": "Gatekeeper"}, user_data)[0]

    authorize_ingress(sec_group_gatekeeper, [
        {"protocol": "tcp", "port": FLASK_PORT, "ip_range": "0.0.0.0/0"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    return gatekeeper_instance

def create_proxy(vpc_id: str, subnet_id: str, key_name: str, user_data: str, jumpbox_private_ip: str, gatekeeper_private_ip: str, infra_info: InfraInfo):
    sec_group_proxy = create_security_group(
        "sec_group_proxy", "Security group for Proxy node", vpc_id)
    infra_info.security_groups_ids.append(sec_group_proxy.id)

    proxy_instance = create_ubuntu_instances("t2.large", 1, 1, key_name, False, subnet_id,
                                             sec_group_proxy, infra_info.instances_tags | {"Name": "Proxy"}, user_data)[0]

    authorize_ingress(sec_group_proxy, [
        {"protocol": "tcp", "port": FLASK_PORT,
            "ip_range": gatekeeper_private_ip + "/32"},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    return proxy_instance

def create_manager(vpc_id: str, subnet_id: str, subnet_cidr: str, key_name: str, user_data: str, jumpbox_private_ip: str, proxy_private_ip: str, infra_info: InfraInfo):
    sec_group_manager = create_security_group(
        "sec_group_manager", "Security group for Manager node", vpc_id)
    infra_info.security_groups_ids.append(sec_group_manager.id)

    manager_instance = create_ubuntu_instances(
        "t2.small", 1, 1, key_name, False, subnet_id, sec_group_manager, infra_info.instances_tags | {"Name": "Manager"}, user_data)[0]

    authorize_ingress(sec_group_manager, [
        {"protocol": "tcp", "port": MYSQL_PORT,
            "ip_range": proxy_private_ip + "/32"},
        {"protocol": "tcp", "port": NDB_MANAGER_PORT, "ip_range": subnet_cidr},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    return manager_instance

def create_data_nodes(vpc_id: str, subnet_id: str, subnet_cidr: str, key_name: str, user_data: str, jumpbox_private_ip: str, proxy_private_ip: str, infra_info: InfraInfo):
    sec_group_data_node = create_security_group(
        "sec_group_data_node", "Security group for Data nodes", vpc_id)
    infra_info.security_groups_ids.append(sec_group_data_node.id)

    data_nodes_instances = create_ubuntu_instances(
        "t2.small", 3, 3, key_name, False, subnet_id, sec_group_data_node, infra_info.instances_tags, user_data)

    authorize_ingress(sec_group_data_node, [
        {"protocol": "tcp", "port": MYSQL_PORT,
            "ip_range": proxy_private_ip + "/32"},
        {"protocol": "tcp", "port": NDB_DATA_NODE_PORT, "ip_range": subnet_cidr},
        {"protocol": "tcp", "port": SSH_PORT,
            "ip_range": jumpbox_private_ip + "/32"}
    ])

    return data_nodes_instances

def create_instances(infra_info: InfraInfo):
    """
    Create instances.

    @param infra_info:InfraInfo     object that will hold infrastructure information

    @return                        object containing infrastructure information
    """
    vpc_id = get_vpc_id()

    subnets = get_subnets(vpc_id)
    subnet_id = subnets[0]['SubnetId']
    subnet_cidr = subnets[0]['CidrBlock']

    key_name = get_key_pair_name()

    infra_info.instances_tags = {"Purpose": "LOG8415E-Project"}

    jumpbox_instance, jumpbox_pub_key = create_jumpbox(
        vpc_id, subnet_id, subnet_cidr, key_name, infra_info)
    jumpbox_private_ip = jumpbox_instance.private_ip_address

    user_data = f"#!/bin/bash\njumpbox_pub_key={jumpbox_pub_key}\necho -e $jumpbox_pub_key >> ~/.ssh/authorized_keys"

    standalone_mysql_instance  = create_standalone_mysql(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, infra_info)

    gatekeeper_instance = create_gatekeeper(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, infra_info)
    gatekeeper_private_ip = gatekeeper_instance.private_ip_address

    proxy_instance = create_proxy(vpc_id, subnet_id, key_name, user_data, jumpbox_private_ip, gatekeeper_private_ip, infra_info)
    proxy_private_ip = proxy_instance.private_ip_address

    manager_instance = create_manager(vpc_id, subnet_id, subnet_cidr, key_name, user_data, jumpbox_private_ip, proxy_private_ip, infra_info)
    data_nodes_instances = create_data_nodes(vpc_id, subnet_id, subnet_cidr, key_name, user_data, jumpbox_private_ip, proxy_private_ip, infra_info)

    instances_hostnames = {
        "jumpbox": {"host": jumpbox_private_ip, "dns": jumpbox_instance.public_dns_name},
        "standalone_mysql": {"host": standalone_mysql_instance.private_ip_address, "dns": standalone_mysql_instance.public_dns_name},
        "gatekeeper": {"host": gatekeeper_private_ip, "dns": gatekeeper_instance.public_dns_name},
        "proxy":  {"host": proxy_private_ip},
        "manager":  {"host": manager_instance.private_ip_address},
        "data_nodes": [{"host": instance.private_ip_address} for instance in data_nodes_instances]
    }

    print("Waiting for instances to be in a running state")

    filters = filters_from_tags(infra_info.instances_tags)
    instances_ids = get_instances_ids(filters)
    stopped_instances = stopped_instances_ids(instances_ids)
    if len(stopped_instances) > 0:
        raise Exception("One of the instances stopped")

    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(InstanceIds=instances_ids)

    print("done\n")

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
        (gatekeeper_host, get_absolute_path('scripts/setup_gatekeeper.sh'))
        (proxy_host, get_absolute_path('scripts/setup_proxy.sh'))
        (manager_host, get_absolute_path('scripts/setup_ndb_cluster_manager.sh'))
    ].extend(
        [
            (data_nodes_host[i], get_absolute_path(
                'scripts/setup_ndb_cluster_data_node.sh'))
            for i in range(len(data_nodes_host))
        ]
    )

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

        script = ''
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

        print(f"Executing setup script of host {host}. It may take some time.")
        _, stdout, stderr = client.exec_command(
            command=jumpbox_script.replace('$script', script), get_pty=True)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            all_stderr.append(stderr)
            print("done\n")
        else:
            for line in stderr:
                print(line)
            raise Exception(f"Failed to setup host {host}")

    stderr_lines = []
    for stderr in all_stderr:
        stderr_lines.extend(stderr.readlines())

    return stderr_lines


if __name__ == '__main__':

    # Necessary information to teardown infra
    infra_info = InfraInfo(
        security_groups_ids=[],
        instances_tags={},
    )

    infra_info.instances_tags = {"Purpose": "LOG8415E-Project"}

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