#!/bin/bash

# To prevent interactive pop up with services to restart
sudo sed -i "s/\#\$nrconf{restart} = 'i'/\$nrconf{restart} = 'l'/" /etc/needrestart/needrestart.conf

sudo apt update
sudo apt install -y tinyproxy

sudo tee /etc/tinyproxy/tinyproxy.conf > /dev/null <<EOF
Port $port
DefaultErrorFile "/usr/share/tinyproxy/default.html"
PidFile "/run/tinyproxy/tinyproxy.pid"
LogFile "/var/log/tinyproxy/tinyproxy.log"
Timeout 600
Allow $cidr
ViaProxyName "tinyproxy"
Filter "/etc/tinyproxy/filter"
ConnectPort 443
FilterDefaultDeny Yes
EOF

sudo tee /etc/tinyproxy/filter > /dev/null <<EOF
*\.archive.ubuntu.com$
^security.ubuntu.com$
^github.com$
^dev.mysql.com$
^cdn.mysql.com$
^pypi.org$
^files.pythonhosted.org$
EOF

sudo systemctl stop tinyproxy
sudo pkill -f tinyproxy
sudo systemctl start tinyproxy
