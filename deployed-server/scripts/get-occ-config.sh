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

read -a Controller_hosts_a <<< $CONTROLLER_HOSTS
read -a Compute_hosts_a <<< $COMPUTE_HOSTS
read -a BlockStorage_hosts_a <<< $BLOCKSTORAGE_HOSTS
read -a ObjectStorage_hosts_a <<< $OBJECTSTORAGE_HOSTS
read -a CephStorage_hosts_a <<< $CEPHSTORAGE_HOSTS

roles="Controller Compute BlockStorage ObjectStorage CephStorage"
admin_user_id=$(openstack user show admin -c id -f value)
admin_project_id=$(openstack project show admin -c id -f value)

function check_stack {
    local stack_to_check=$1

    if [ "$stack_to_check" = "|" ]; then
        echo Stack not created
        return 1
    fi

    echo Checking if $1 stack is created
    set +e
    heat resource-list $stack_to_check
    rc=$?
    set -e

    if [ ! "$rc" = "0" ]; then
        echo Stack $1 not yet created
    fi

    return $rc
}


for role in $roles; do
    while ! check_stack overcloud; do
        sleep $SLEEP_TIME
    done

    rg_stack=$(heat resource-list overcloud | grep " $role " | awk '{print $4}')
    while ! check_stack $rg_stack; do
        sleep $SLEEP_TIME
        rg_stack=$(heat resource-list overcloud | grep " $role " | awk '{print $4}')
    done

    stacks=$(heat resource-list $rg_stack | grep OS::TripleO::$role | awk '{print $4}')

    i=0

    for stack in $stacks; do
        server_resource_name=$role
        if [ "$server_resource_name" = "Compute" ]; then
            server_resource_name="NovaCompute"
        fi

        server_stack=$(heat resource-list $stack | grep " $server_resource_name " | awk '{print $4}')
        while ! check_stack $server_stack; do
            sleep $SLEEP_TIME
            server_stack=$(heat resource-list $stack | grep " $server_resource_name " | awk '{print $4}')
        done

        deployed_server_stack=$(heat resource-list $server_stack | grep "deployed-server" | awk '{print $4}')

        echo "======================"
        echo "$role$i os-collect-config.conf configuration:"

        config="
[DEFAULT]
collectors=heat
command=os-refresh-config
polling_interval=30

[heat]
user_id=$admin_user_id
password=$OS_PASSWORD
auth_url=$OS_AUTH_URL
project_id=$admin_project_id
stack_id=$deployed_server_stack
resource_name=deployed-server-config"

        echo "$config"
        echo "======================"
        echo


        host=
        eval host=\${${role}_hosts_a[i]}
        if [ -n "$host" ]; then
            # Delete the os-collect-config.conf template so our file won't get
            # overwritten
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo /bin/rm -f /usr/libexec/os-apply-config/templates/etc/os-collect-config.conf
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host "echo \"$config\" > os-collect-config.conf"
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo cp os-collect-config.conf /etc/os-collect-config.conf
            ssh $SSH_OPTIONS -i $SUBNODES_SSH_KEY $host sudo systemctl restart os-collect-config
        fi

        let i+=1

    done

done
