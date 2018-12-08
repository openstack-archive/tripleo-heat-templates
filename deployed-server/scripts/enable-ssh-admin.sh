#!/bin/bash

set -eu

# whitespace (space or newline) separated list
OVERCLOUD_HOSTS=${OVERCLOUD_HOSTS:-""}
OVERCLOUD_SSH_USER=${OVERCLOUD_SSH_USER:-"$USER"}
# this is just for compatibility with CI
SUBNODES_SSH_KEY=${SUBNODES_SSH_KEY:-"$HOME/.ssh/id_rsa"}
# this is the intended variable for overriding
OVERCLOUD_SSH_KEY=${OVERCLOUD_SSH_KEY:-"$SUBNODES_SSH_KEY"}
SSH_TIMEOUT_OPTIONS=${SSH_TIMEOUT_OPTIONS:-"-o ConnectionAttempts=6 -o ConnectTimeout=30"}
SSH_HOSTKEY_OPTIONS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
SHORT_TERM_KEY_COMMENT="TripleO split stack short term key"
SLEEP_TIME=5

# needed to handle where python lives
function get_python() {
  command -v python3 || command -v python2 || command -v python || exit 1
}

function overcloud_ssh_hosts_json {
    echo "$OVERCLOUD_HOSTS" | $(get_python) -c '
from __future__ import print_function
import json, re, sys
print(json.dumps(re.split("\s+", sys.stdin.read().strip())))'
}

function overcloud_ssh_key_json {
    # we pass the contents to Mistral instead of just path, otherwise
    # the key file would have to be readable for the mistral user
    cat "$1" | $(get_python) -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

function workflow_finished {
    local execution_id="$1"
    openstack workflow execution show -f shell $execution_id | grep 'state="SUCCESS"' > /dev/null
}

function generate_short_term_keys {
    local tmpdir=$(mktemp -d)
    ssh-keygen -N '' -t rsa -b 4096 -f "$tmpdir/id_rsa" -C "$SHORT_TERM_KEY_COMMENT" > /dev/null
    echo "$tmpdir"
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

SHORT_TERM_KEY_DIR=$(generate_short_term_keys)
SHORT_TERM_KEY_PRIVATE="$SHORT_TERM_KEY_DIR/id_rsa"
SHORT_TERM_KEY_PUBLIC="$SHORT_TERM_KEY_DIR/id_rsa.pub"
SHORT_TERM_KEY_PUBLIC_CONTENT=$(cat $SHORT_TERM_KEY_PUBLIC)

for HOST in $OVERCLOUD_HOSTS; do
    echo "Inserting TripleO short term key for $HOST"
    # prepending an extra newline so that if authorized_keys didn't
    # end with a newline previously, we don't end up garbling it up
    ssh $SSH_TIMEOUT_OPTIONS $SSH_HOSTKEY_OPTIONS -i "$OVERCLOUD_SSH_KEY" -l "$OVERCLOUD_SSH_USER" "$HOST" "echo -e '\n$SHORT_TERM_KEY_PUBLIC_CONTENT' >> \$HOME/.ssh/authorized_keys"
done

echo "Starting ssh admin enablement workflow"
EXECUTION_PARAMS="{\"ssh_user\": \"$OVERCLOUD_SSH_USER\", \"ssh_servers\": $(overcloud_ssh_hosts_json), \"ssh_private_key\": $(overcloud_ssh_key_json "$SHORT_TERM_KEY_PRIVATE")}"
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
echo  # newline after the previous dots

for HOST in $OVERCLOUD_HOSTS; do
    echo "Removing TripleO short term key from $HOST"
    ssh $SSH_TIMEOUT_OPTIONS $SSH_HOSTKEY_OPTIONS -i "$OVERCLOUD_SSH_KEY" -l "$OVERCLOUD_SSH_USER" "$HOST" "sed -i -e '/$SHORT_TERM_KEY_COMMENT/d' \$HOME/.ssh/authorized_keys"
done

echo "Removing short term keys locally"
rm -r "$SHORT_TERM_KEY_DIR"

echo "Success."
