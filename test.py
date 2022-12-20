import os
import sys
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import errorcode
import paramiko

load_dotenv()

USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')
HOST = os.getenv('HOST')
DATABASE = os.getenv('DATABASE')

cnx = mysql.connector.connect(user=USER, password=PASSWORD, host=HOST)
cursor = cnx.cursor()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

pKey_filename = os.path.join(sys.path[0], 'labsuser.pem')


print("SSH connection to instance\n")
client.connect(hostname=HOST, port=22, username='ubuntu', key_filename=pKey_filename)

def create_sakila_db():
    all_stderr = []
    script = ''

    print("Downloading sakila")
    with open(os.path.join(sys.path[0], 'download_sakila.sh'), 'r') as f:
        script = f.read()
    _, stdout, stderr = client.exec_command(command=script, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        all_stderr.append(stderr)
        print("done\n")
    else:
        for line in stderr:
            print(line)
        raise Exception("Failed to download sakila archive")

    print("Creating DB sakila")
    script = f"mysql -u {USER} -p'{PASSWORD}' -e \"source ~/sakila-db/sakila-schema.sql;\""
    _, stdout, stderr = client.exec_command(command=script, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        all_stderr.append(stderr)
        print("done\n")
    else:
        for line in stderr:
            print(line)
        raise Exception("Failed to create DB sakila")

    print("Populating sakila")
    script = f"mysql -u {USER} -p'{PASSWORD}' -e \"source ~/sakila-db/sakila-data.sql;\""
    _, stdout, stderr = client.exec_command(command=script, get_pty=True)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status == 0:
        all_stderr.append(stderr)
        print("done\n")
    else:
        for line in stderr:
            print(line)
        raise Exception("Failed to populate DB sakila")

    stderr_lines = []
    for stderr in all_stderr:
        stderr_lines.extend(stderr.readlines()) 

    return stderr_lines


try:
    cursor.execute(f"USE {DATABASE}")
except mysql.connector.Error as err:
    print(f"Database {DATABASE} does not exists.\n")
    if err.errno == errorcode.ER_BAD_DB_ERROR:
        stderr = create_sakila_db()
        print("Error output:\n")
        if len(stderr) == 0:
            print("None")
        else :
            for line in stderr:
                print(line)
        print(f"Database {DATABASE} created successfully.\n")

        cnx.database = DATABASE
    else:
        print(err)
        exit(1)


cursor.close()
cnx.close()


# def create_sakila_db(cursor):
#     try:
#         # with open(os.path.join(sys.path[0], 'sakila-db/sakila-schema.sql'), 'r') as f:
#             query = "SOURCE ~/sakila-db/sakila-schema.sql"
#             cursor.execute(query)
#     except mysql.connector.Error as err:
#         print("Failed creating database: {}".format(err))
#         exit(1)
# try:
#     # with open(os.path.join(sys.path[0], 'sakila-db/sakila-data.sql'), 'r') as f:
#         query = "SOURCE ~/sakila-db/sakila-data.sql"
#         cursor.execute(query)
# except mysql.connector.Error as err:
#     print("Failed adding data: {}".format(err))
#     exit(1)

            # lines = f.readlines()
            # print(len(lines))
            # query = ''
            # for line in lines:
            #     if line.strip() == '' or line.strip().startswith("--"):
            #         continue

            #     query = query + '\n' + line
            #     print(line)
            #     if line.endswith(';'):
            #         print(query)
            #         cursor.execute(query)
            #         query = ''
