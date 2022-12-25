#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

sudo apt-get update
sudo apt install python3-pip -y

cd LOG8415E-Project
pip install -r proxy_requirements.txt

export USER=$username
export PASSWORD=$user_password
export MANAGER_HOST=$manager_host
export DATA_NODES_HOST=$data_nodes_host
export DATABASE=sakila
python3 patterns_app/remote_proxy_app.py