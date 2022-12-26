#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e


ssh ubuntu@$host -o StrictHostKeyChecking=no 'bash -s' << EOF
$script
EOF