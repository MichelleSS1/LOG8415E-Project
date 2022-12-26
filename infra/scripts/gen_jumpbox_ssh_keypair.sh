#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

ssh-keygen -q -t rsa -C ubuntu@jumpbox -f /home/ubuntu/.ssh/id_rsa -N '' <<< $'\ny' >/dev/null 2>&1
cat /home/ubuntu/.ssh/id_rsa.pub
