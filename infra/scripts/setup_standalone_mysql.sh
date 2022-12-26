#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# To prevent interactive pop up with services to restart
sudo sed -i "s/\#\$nrconf{restart} = 'i'/\$nrconf{restart} = 'l'/" /etc/needrestart/needrestart.conf

sudo apt update
sudo apt install mysql-server -y
sudo systemctl start mysql.service
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$root_password';"

git clone https://github.com/MichelleSS1/LOG8415E-Project.git
# To run mysql_secure_installation without prompt
sudo apt install -y expect
sed -i "s/root_password/$root_password/" ./LOG8415E-Project/script.exp
sudo ./LOG8415E-Project/script.exp

mysql -u root -p'$root_password' -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH auth_socket;"

# Create a mysql user for other programs
sudo mysql -e "CREATE USER '$username'@'%' IDENTIFIED BY '$user_password';"
sudo mysql -e "GRANT ALL PRIVILEGES ON *.* TO '$username'@'%'; FLUSH PRIVILEGES;"

# Enable remote access
sudo sed -i "s/.*bind-address.*/bind-address = 0.0.0.0/" /etc/mysql/mysql.conf.d/mysqld.cnf
