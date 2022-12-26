#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

sudo apt-get update
sudo apt install -y python3-pip

git clone https://github.com/MichelleSS1/LOG8415E-Project.git
cd LOG8415E-Project
pip install -r proxy_requirements.txt

export USER=$username
export PASSWORD=$user_password
export MANAGER_HOST=$manager_host
export DATA_NODES_HOST=$data_nodes_host
export DATABASE=sakila
nohup python3 patterns_app/remote_proxy_app.py > flask_log.txt 2>&1 &
