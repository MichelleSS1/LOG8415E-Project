import os
from flask import Flask, request
import requests
import json

app = Flask(__name__)

PROXY_HOST = os.getenv('PROXY_HOST')

class LocalProxy:
    def __send_query(self, url, query):
        payload = json.dumps({
            "query": query
        })
        headers = {
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        return json.loads(response.text)

    def write_query(self, query: str):
        url = f"http://{PROXY_HOST}:5000/write-query"
        return self.__send_query(url, query)

    def read_query(self, query: str, method_id=0):
        url = f"http://{PROXY_HOST}:5000/read-query?method_id={method_id}"
        return self.__send_query(url, query)

local_proxy = LocalProxy()

@app.route('/')
def health_check():
    return "Healthy!"

@app.route('/write-query', methods=['POST'])
def execute_write_query():
    query = request.get_json()['query']
    return local_proxy.write_query(query)

@app.route('/read-query', methods=['POST'])
def execute_read_query():
    method_id = request.args.get('method_id')
    query = request.get_json()['query']
    return local_proxy.read_query(query, method_id)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)