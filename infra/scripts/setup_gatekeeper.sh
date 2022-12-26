#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

sudo apt-get update
sudo apt install python3-pip -y

git clone https://github.com/MichelleSS1/LOG8415E-Project.git
cd LOG8415E-Project
pip install -r gatekeeper_requirements.txt

export PROXY_HOST=$proxy_host
nohup python3 patterns_app/gatekeeper_app.py > flask_log.txt 2>&1 &
