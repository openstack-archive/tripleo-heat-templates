#!/bin/bash

set -eux

SLEEP_TIME=5

CONTROLLER_HOSTS=${CONTROLLER_HOSTS:-""}
COMPUTE_HOSTS=${COMPUTE_HOSTS:-""}
BLOCKSTORAGE_HOSTS=${BLOCKSTORAGE_HOSTS:-""}
OBJECTSTORAGE_HOSTS=${OBJECTSTORAGE_HOSTS:-""}
CEPHSTORAGE_HOSTS=${CEPHSTORAGE_HOSTS:-""}
SUBNODES_SSH_KEY=${SUBNODES_SSH_KEY:-"~/.ssh/id_rsa"}
SSH_OPTIONS="-tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=Verbose -o PasswordAuthentication=no -o ConnectionAttempts=32"
OVERCLOUD_ROLES=${OVERCLOUD_ROLES:-"Controller Compute BlockStorage ObjectStorage CephStorage"}
STACK_NAME=${STACK_NAME:-"overcloud"}

# Set the _hosts vars for the default roles based on the old var names that
# were all caps for backwards compatibility.
Controller_hosts=${Controller_hosts:-"$CONTROLLER_HOSTS"}
Compute_hosts=${Compute_hosts:-"$COMPUTE_HOSTS"}
BlockStorage_hosts=${BlockStorage_hosts:-"$BLOCKSTORAGE_HOSTS"}
ObjectStorage_hosts=${ObjectStorage_hosts:-"$OBJECTSTORAGE_HOSTS"}
CephStorage_hosts=${CephStorage_hosts:-"$CEPHSTORAGE_HOSTS"}

# Set the _hosts_a vars for each role defined
for role in $OVERCLOUD_ROLES; do
    eval "hosts=\${${role}_hosts}"
    read -a ${role}_hosts_a <<< $hosts
done

function check_stack {
    local stack_to_check=${1:-""}

    if [ "$stack_to_check" = "" ]; then
        echo Stack not created
        return 1
    fi

    echo Checking if $1 stack is created
    set +e
    openstack stack resource list $stack_to_check
    rc=$?
    set -e

    if [ ! "$rc" = "0" ]; then
        echo Stack $1 not yet created
    fi

    return $rc
}


for role in $OVERCLOUD_ROLES; do
    while ! check_stack $STACK_NAME; do
        sleep $SLEEP_TIME
    done

    rg_stack=$(openstack stack resource show $STACK_NAME $role -c physical_resource_id -f value)
    while ! check_stack $rg_stack; do
        sleep $SLEEP_TIME
        rg_stack=$(openstack stack resource show $STACK_NAME $role -c physical_resource_id -f value)
    done

    stacks=$(openstack stack resource list $rg_stack -c resource_name -c physical_resource_id -f json | jq -r "sort_by(.resource_name) | .[] | .physical_resource_id")

    i=0

    for stack in $stacks; do
        server_resource_name=$role
        if [ "$server_resource_name" = "Compute" ]; then
            server_resource_name="NovaCompute"
        fi

        server_stack=$(openstack stack resource show $stack $server_resource_name -c physical_resource_id -f value)
        while ! check_stack $server_stack; do
            sleep $SLEEP_TIME
            server_stack=$(openstack stack resource show $stack $server_resource_name -c physical_resource_id -f value)
        done

        while true; do
            deployed_server_metadata_url=$(openstack stack resource metadata $server_stack deployed-server | jq -r '.["os-collect-config"].request.metadata_url')
            if [ "$deployed_server_metadata_url" = "null" ]; then
                continue
            else
                break
            fi
        done

        echo "======================"
        echo "$role$i deployed-server.json configuration:"

        config="{
  \"os-collect-config\": {
    \"collectors\": [\"request\", \"local\"],
    \"request\": {
      \"metadata_url\": \"$deployed_server_metadata_url\"
    }
  }
}"

        echo "$config"
        echo "======================"
        echo


        host=
        eval "host=\${${role}_hosts_a[$i]}"
        if [ -n "$host" ]; then
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host "echo '$config' > deployed-server.json"
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo mkdir -p -m 0700 /var/lib/os-collect-config/local-data/ || true
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo cp deployed-server.json /var/lib/os-collect-config/local-data/deployed-server.json
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo systemctl start os-collect-config
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo systemctl enable os-collect-config
        fi

        ((i++))

    done

done
