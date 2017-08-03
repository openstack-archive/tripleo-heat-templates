#!/bin/bash

set -eu

# whitespace (space or newline) separated list
OVERCLOUD_HOSTS=${OVERCLOUD_HOSTS:-""}
OVERCLOUD_SSH_USER=${OVERCLOUD_SSH_USER:-"$USER"}
# this is just for compatibility with CI
SUBNODES_SSH_KEY=${SUBNODES_SSH_KEY:-"$HOME/.ssh/id_rsa"}
# this is the intended variable for overriding
OVERCLOUD_SSH_KEY=${OVERCLOUD_SSH_KEY:-"$SUBNODES_SSH_KEY"}

SLEEP_TIME=5

function overcloud_ssh_hosts_json {
    echo "$OVERCLOUD_HOSTS" | python -c '
from __future__ import print_function
import json, re, sys
print(json.dumps(re.split("\s+", sys.stdin.read().strip())))'
}

function overcloud_ssh_key_json {
    # we pass the contents to Mistral instead of just path, otherwise
    # the key file would have to be readable for the mistral user
    cat "$OVERCLOUD_SSH_KEY" | python -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

function workflow_finished {
    local execution_id="$1"
    openstack workflow execution show -f shell $execution_id | grep 'state="SUCCESS"' > /dev/null
}

if [ -z "$OVERCLOUD_HOSTS" ]; then
    echo 'Please set $OVERCLOUD_HOSTS'
    exit 1
fi

echo "Starting workflow to create ssh admin on deployed servers."
echo "SSH user: $OVERCLOUD_SSH_USER"
echo "SSH key file: $OVERCLOUD_SSH_KEY"
echo "Hosts: $OVERCLOUD_HOSTS"
echo

EXECUTION_PARAMS="{\"ssh_user\": \"$OVERCLOUD_SSH_USER\", \"ssh_servers\": $(overcloud_ssh_hosts_json), \"ssh_private_key\": $(overcloud_ssh_key_json)}"
EXECUTION_CREATE_OUTPUT=$(openstack workflow execution create -f shell -d 'deployed server ssh admin creation' tripleo.access.v1.enable_ssh_admin "$EXECUTION_PARAMS")
echo "$EXECUTION_CREATE_OUTPUT"
EXECUTION_ID=$(echo "$EXECUTION_CREATE_OUTPUT" | grep '^id=' | awk '-F"' '{ print $2 }')

if [ -z "$EXECUTION_ID" ]; then
    echo "Failed to get workflow execution ID for ssh admin creation workflow"
    exit 1
fi

echo -n "Waiting for the workflow execution to finish (id $EXECUTION_ID)."
while ! workflow_finished $EXECUTION_ID; do
    sleep $SLEEP_TIME
    echo -n .
done

echo "Success."
