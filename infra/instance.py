import base64
import boto3

ec2_client = boto3.client('ec2') 
ec2 = boto3.resource('ec2')
elb = boto3.client("elbv2")


def create_ubuntu_instances(
    instance_type:str, 
    min_count:int, 
    max_count:int, 
    key_name:str,
    associate_public_ip:bool, 
    subnet_id:str, 
    security_groups:"list[str]",
    tags:"dict[str, str]",
    user_data:str=""
):
    """
    Create max_count instances, and at least min_count instances if not possible, with instance_type specifying the type
    of machine to be created and security_groups specifying the security groups of each instance. The operating system
    will be ubuntu.
    They will be located in subnet whose id is subnet_id.

    @param instance_type:str            type of instance, specifies the available CPU, memory, etc. ex. t2.micro
    @param min_count:int                create at least this many instances
    @param max_count:int                try to create this many instances
    @param key_name:str                 the name of the key pair used to connect to the instances
    @param associate_public_ip:bool     whether to associate a public ip to the instance
    @param subnet_id:str                subnet where the machines will be located
    @param security_groups:list[str]    security groups ids to be applied ['sg-id1', 'sg-id2']
    @param tags:dict[str, str]          tags to put on instances

    @return                             response containing the instance IDs and other data 
    """
    print("Creating instances of type: ", instance_type)
    instances = ec2.create_instances(
        ImageId='ami-08c40ec9ead489470',
        MinCount=min_count,
        MaxCount=max_count,
        InstanceType=instance_type,
        KeyName=key_name,
        UserData=user_data,
        NetworkInterfaces=[
            {
                'AssociatePublicIpAddress': associate_public_ip,
                'Groups': security_groups,
                'SubnetId': subnet_id,
            },
        ],
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': key,
                        'Value': value
                    }
                    for key, value in tags.items()
                ]
            }
        ]
    )

    i = 0
    for instance in instances:
        ec2.create_tags(Resources=[instance.id], Tags=[
            {
                'Key': 'Name',
                'Value': instance_type.replace('.','-') + '-' + str(i)
            },
        ])
        i += 1

    print("done\n")
    return instances

def stopped_instances_ids(instances_ids:"list[str]"):
    """
    Retrieve instances with state in 'shutting-down' | 'terminated' | 'stopping' | 'stopped'
    among the given list of instances ids

    @param instances_ids:list[str]     List of instances ids among which to look

    @return                            Found ids
    """
    stopped_instances_ids = []
    instances_to_remove = ec2_client.describe_instances(
        Filters=[
            {
                'Name': 'instance-state-name',
                'Values': [
                    'shutting-down', 'terminated', 'stopping', 'stopped'
                ]
            }, 
        ],
        InstanceIds=instances_ids
    )['Reservations']
    if len(instances_to_remove) > 0:
        for instances_block in instances_to_remove:
            for instance in instances_block['Instances']:
                stopped_instances_ids.append(instance['InstanceId'])

    return stopped_instances_ids

def get_instances_ids(filters:"list[dict]"):
    """
    Retrieve instances ids corresponding to filters.

    @return                            Found ids ; all ids if filters empty
    """
    instances_ids = []

    if len(filters) > 0:
        instances = ec2_client.describe_instances(
            Filters=filters
        )['Reservations']
    else:
        instances = ec2_client.describe_instances()['Reservations']

    if len(instances) > 0:
        for instances_block in instances:
            for instance in instances_block['Instances']:
                instances_ids.append(instance['InstanceId'])

    return instances_ids

def terminate_instances(instance_ids:"list[str]"):
    """
    Shuts down one or more instances. This operation is idempotent; if you terminate an instance more than once, each call succeeds.

    @param instance_ids:list    One or more instance IDs.
    @return: dict
    """
    print("Terminating instances")
    response = ec2_client.terminate_instances(InstanceIds=instance_ids)
    
    # Wait for instances to terminate
    waiter = ec2_client.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=instance_ids)

    return response
