import os
import subprocess
import random
import mysql.connector
from flask import Flask, request

app = Flask(__name__)

USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')
DATABASE = os.getenv('DATABASE')
HOSTS = { "manager": os.getenv('MANAGER_HOST') }
HOSTS = HOSTS | { f"data_node_{i}": host for i, host in enumerate(os.getenv("DATA_NODES_HOST").split(',')) }

DIRECT_HIT = 0
RANDOM_HIT = 1
CUSTOM_HIT = 2


def get_server_ping_time(server, count=1, wait_sec=1):
    """

    :rtype: dict or None
    """
    cmd = "ping -c {} -W {} {}".format(count, wait_sec, server).split(' ')
    try:
        output = subprocess.check_output(cmd).decode().strip()
        lines = output.split("\n")
        timing = lines[-1].split()[3].split('/')
        print(timing)
        return float(timing[1]) # avg
    except Exception as e:
        print(e)
        return None

def get_best_ping_time_node(nodes_names: list[str]):
    best_ping_time_node_name = nodes_names[0]
    best_ping_time = 10000.0

    for i in range(len(nodes_names)):
        node_name = nodes_names[i]
        node = HOSTS[node_name]
        ping_time = get_server_ping_time(node)
        if ping_time < best_ping_time:
            best_ping_time_node_name = node_name
            best_ping_time = ping_time

    return best_ping_time_node_name, best_ping_time

def query_db(host: str, host_name:str, query: str):
    cnx = mysql.connector.connect(user=USER, password=PASSWORD, host=host, database=DATABASE)
    cursor = cnx.cursor()

    try:
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        cnx.close()
        return { "node": f"{host_name}", "result": result }
    except mysql.connector.Error as err:
        cursor.close()
        cnx.close()
        return { "node": f"{host_name}", "result": [f"Failed executing query: {err}"] }

def direct_hit(query):
    return query_db(HOSTS["manager"], "manager", query)

def random_hit(query):
    data_node_host_name = random.choice(list(HOSTS.keys()).remove("manager"))
    print(f"Chosen data node: {data_node_host_name}")
    return query_db(HOSTS[data_node_host_name], data_node_host_name, query)

def custom_hit(query):
    data_node_host_name, ping_time = get_best_ping_time_node(list(HOSTS.keys()).remove("manager"))
    print(f"Chosen data node: {data_node_host_name}")
    response = query_db(HOSTS[data_node_host_name], data_node_host_name, query)
    response['ping_time'] = ping_time
    return response


@app.route('/')
def health_check():
    return "Healthy!"

@app.route('/write-query', methods=['POST'])
def execute_write_query():
    query = request.get_json()['query']
    return direct_hit(query)

@app.route('/read-query', methods=['POST'])
def execute_read_query():
    method_id = request.args.get('method_id')
    if method_id != None and method_id.isdigit():
        method_id = int(method_id)

    query = request.get_json()['query']
    
    match method_id:
        case 0:
            return direct_hit(query)
        case 1:
            return random_hit(query)
        case 2:
            return custom_hit(query)
        case _:
            return direct_hit(query)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)