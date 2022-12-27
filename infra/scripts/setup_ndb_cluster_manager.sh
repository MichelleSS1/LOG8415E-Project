#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# To prevent interactive pop up with services to restart
sudo sed -i "s/\#\$nrconf{restart} = 'i'/\$nrconf{restart} = 'l'/" /etc/needrestart/needrestart.conf

# Download and install package
wget https://dev.mysql.com/get/Downloads/MySQL-Cluster-8.0/mysql-cluster-community-management-server_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-cluster-community-management-server_8.0.31-1ubuntu22.04_amd64.deb

git clone https://github.com/MichelleSS1/LOG8415E-Project.git

# Directory of the configuration file
sudo mkdir /var/lib/mysql-cluster
sudo cp LOG8415E-Project/infra/config_files/config.ini /var/lib/mysql-cluster/config.ini
sudo sed -i "s/manager_host/$manager_host/" /var/lib/mysql-cluster/config.ini
sudo sed -i "s/data_node1_host/$data_node1_host/" /var/lib/mysql-cluster/config.ini
sudo sed -i "s/data_node2_host/$data_node2_host/" /var/lib/mysql-cluster/config.ini
sudo sed -i "s/data_node3_host/$data_node3_host/" /var/lib/mysql-cluster/config.ini
sudo cp LOG8415E-Project/infra/config_files/ndb_mgmd.service /etc/systemd/system/ndb_mgmd.service
sudo systemctl daemon-reload
sudo systemctl enable ndb_mgmd
sudo systemctl start ndb_mgmd


# Setup of mysql
wget https://dev.mysql.com/get/Downloads/MySQL-Cluster-8.0/mysql-cluster_8.0.31-1ubuntu22.04_amd64.deb-bundle.tar

mkdir install
tar -xvf mysql-cluster_8.0.31-1ubuntu22.04_amd64.deb-bundle.tar -C install/
cd install

sudo apt update
sudo apt install -y libaio1 libmecab2

sudo dpkg -i mysql-common_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-cluster-community-client-plugins_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-cluster-community-client-core_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-cluster-community-client_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-client_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-cluster-community-server-core_8.0.31-1ubuntu22.04_amd64.deb

# To prevent prompt
sudo apt install dialog apt-utils -y
sudo debconf-set-selections <<< "mysql-cluster-community-server mysql-cluster-community-server/root-pass password password"
sudo debconf-set-selections <<< "mysql-cluster-community-server mysql-cluster-community-server/re-root-pass password password"
sudo debconf-set-selections <<< "mysql-cluster-community-server mysql-server/default-auth-override select Use Strong Password Encryption (RECOMMENDED)"

sudo dpkg -i mysql-cluster-community-server_8.0.31-1ubuntu22.04_amd64.deb
sudo dpkg -i mysql-server_8.0.31-1ubuntu22.04_amd64.deb

sudo -i /bin/bash  -c "cat /home/ubuntu/LOG8415E-Project/infra/config_files/mysql.cnf >> /etc/mysql/my.cnf"
sudo sed -i "s/manager_host/$manager_host/" /etc/mysql/my.cnf
sudo sed -i "s/proxy_host/$proxy_host/" /etc/mysql/my.cnf
sudo systemctl restart mysql
sudo systemctl enable mysql

# Create a mysql user for other programs
mysql -u root -p"$root_password" -e "CREATE USER '$username'@'%' IDENTIFIED BY '$user_password';"
mysql -u root -p"$root_password" -e "GRANT ALL PRIVILEGES ON *.* TO '$username'@'%'; FLUSH PRIVILEGES;"
