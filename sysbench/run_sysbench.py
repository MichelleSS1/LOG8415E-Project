import json
import os
import sys
import paramiko


def get_absolute_path(relative_path: str):
    return os.path.join(sys.path[0], relative_path)

with open(get_absolute_path('../infra/instances_hostnames.json'), 'r') as f:
    instances_hostnames = json.load(f)
jumpbox_dns = instances_hostnames['jumpbox']['dns']
standalone_mysql_dns = instances_hostnames['standalone_mysql']['dns']
manager_host = instances_hostnames['manager']['host']

pKey_filename = get_absolute_path('../pkey.pem')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

all_stderr = []

print("SSH connection to standalone mysql")
client.connect(hostname=standalone_mysql_dns,
                port=22, username='ubuntu', key_filename=pKey_filename)

with open(get_absolute_path('sysbench_standalone.sh'), 'r') as f:
    script = f.read()
    script = script.replace('$username', os.getenv('USER'))
    script = script.replace('$user_password', os.getenv('PASSWORD'))

print(f"Executing sysbench on standalone mysql. It may take some time.")
_, stdout, stderr = client.exec_command(command=script, get_pty=True)
exit_status = stdout.channel.recv_exit_status()
if exit_status == 0:
    all_stderr.append(stderr)
    print("done\n")
else:
    for line in stderr.readlines():
        print(line)
    raise Exception(f"Failed to run sysbench on standalone mysql")

print("Extracting sysbench result")
_, stdout, stderr = client.exec_command(command="cat ~/sysbench_result.txt", get_pty=True)
exit_status = stdout.channel.recv_exit_status()
if exit_status == 0:
    all_stderr.append(stderr)
    with open(get_absolute_path('standalone_sysbench_result.txt'), 'w') as f:
        f.writelines(stdout.readlines())
    print("done\n")
else:
    for line in stderr.readlines():
        print(line)
    raise Exception(f"Failed to run sysbench on standalone mysql")

print("SSH connection to cluster manager through jumpbox")
client.connect(hostname=jumpbox_dns,
                port=22, username='ubuntu', key_filename=pKey_filename)

with open(get_absolute_path('../infra/jumpbox_ssh_helper.sh'), 'r') as f:
    script = f.read()
    script = script.replace('$host', manager_host)

with open(get_absolute_path('sysbench_cluster.sh'), 'r') as f:
    script = script.replace('$script', f.read())
    script = script.replace('$username', os.getenv('USER'))
    script = script.replace('$user_password', os.getenv('PASSWORD'))


script = script + '\n' + f"exit; scp ubuntu@{manager_host}:sysbench_result.txt ./cluster_sysbench_result.txt"

print(f"Executing sysbench on cluster manager. It may take some time.")
_, stdout, stderr = client.exec_command(command=script, get_pty=True)
exit_status = stdout.channel.recv_exit_status()
if exit_status == 0:
    all_stderr.append(stderr)
    print("done\n")
else:
    for line in stderr.readlines():
        print(line)
    raise Exception(f"Failed to run sysbench on cluster manager")

print("Extracting sysbench result")
_, stdout, stderr = client.exec_command(command="cat ~/cluster_sysbench_result.txt", get_pty=True)
exit_status = stdout.channel.recv_exit_status()
if exit_status == 0:
    all_stderr.append(stderr)
    with open(get_absolute_path('cluster_sysbench_result.txt'), 'w') as f:
        f.writelines(stdout.readlines())
    print("done\n")
else:
    for line in stderr.readlines():
        print(line)
    raise Exception(f"Failed to run sysbench on cluster")

stderr_lines = []
for stderr in all_stderr:
    stderr_lines.extend(stderr.readlines())

print("Error output:\n")
for line in stderr_lines:
    print(line)
