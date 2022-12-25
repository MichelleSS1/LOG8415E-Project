#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

sudo apt update
sudo apt install -y sysbench

sysbench oltp_read_write --tables=8 --threads=6 --time=360 --max-requests=0 --mysql-db=sakila --mysql-user=$username --mysql-password='$user_password'  --mysql_storage_engine=NDBCLUSTER prepare
sysbench oltp_read_write --tables=8 --threads=6 --time=360 --max-requests=0 --mysql-db=sakila --mysql-user=$username --mysql-password='$user_password'  --mysql_storage_engine=NDBCLUSTER run > sysbench_result.txt
