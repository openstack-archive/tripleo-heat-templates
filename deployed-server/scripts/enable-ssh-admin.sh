#!/bin/bash

set -eu

OVERCLOUD_PLAN=${OVERCLOUD_PLAN:-"overcloud"}
# whitespace (space or newline) separated list
OVERCLOUD_HOSTS=${OVERCLOUD_HOSTS:-""}
OVERCLOUD_SSH_USER=${OVERCLOUD_SSH_USER:-"$USER"}

function get_python() {
  command -v python3 || command -v python2 || command -v python || exit 1
}

function overcloud_ssh_hosts_json {
    echo "$OVERCLOUD_HOSTS" | $(get_python) -c '
import json, re, sys
print(json.dumps(re.split("\s+", sys.stdin.read().strip())))'
}

echo "Running playbook to create ssh admin on deployed servers."
echo "SSH user: $OVERCLOUD_SSH_USER"
echo "Hosts: $OVERCLOUD_HOSTS"

extra_vars="{\"ssh_user\": \"$OVERCLOUD_SSH_USER\", \"ssh_servers\": $(overcloud_ssh_hosts_json), \"tripleo_cloud_name\": \"$OVERCLOUD_PLAN\"}"

ansible-playbook /usr/share/ansible/tripleo-playbooks/cli-enable-ssh-admin.yaml -e "$extra_vars"
