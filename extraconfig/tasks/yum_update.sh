#!/bin/bash

# A heat-config-script which runs yum update during a stack-update.
# Inputs:
#   deploy_action - yum will only be run if this is UPDATE
#   update_identifier - yum will only run for previously unused values of update_identifier
#   command - yum sub-command to run, defaults to "update"
#   command_arguments - yum command arguments, defaults to ""

echo "Started yum_update.sh on server $deploy_server_id at `date`"
echo -n "false" > $heat_outputs_path.update_managed_packages

if [[ -z "$update_identifier" ]]; then
    echo "Not running due to unset update_identifier"
    exit 0
fi

timestamp_dir=/var/lib/overcloud-yum-update
mkdir -p $timestamp_dir

# sanitise to remove unusual characters
update_identifier=${update_identifier//[^a-zA-Z0-9-_]/}

# seconds to wait for this node to rejoin the cluster after update
cluster_start_timeout=600
galera_sync_timeout=1800
cluster_settle_timeout=1800

timestamp_file="$timestamp_dir/$update_identifier"
if [[ -a "$timestamp_file" ]]; then
    echo "Not running for already-run timestamp \"$update_identifier\""
    exit 0
fi
touch "$timestamp_file"

command_arguments=${command_arguments:-}

list_updates=$(yum list updates)

if [[ "$list_updates" == "" ]]; then
    echo "No packages require updating"
    exit 0
fi

pacemaker_status=$(systemctl is-active pacemaker)

# Fix the redis/rabbit resource start/stop timeouts. See https://bugs.launchpad.net/tripleo/+bug/1633455
# and https://bugs.launchpad.net/tripleo/+bug/1634851
if [[ "$pacemaker_status" == "active" && \
      "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]] ; then
    if pcs resource show rabbitmq | grep -E "start.*timeout=100"; then
        pcs resource update rabbitmq op start timeout=200s
    fi
    if pcs resource show rabbitmq | grep -E "stop.*timeout=90"; then
        pcs resource update rabbitmq op stop timeout=200s
    fi
    if pcs resource show redis | grep -E "start.*timeout=120"; then
        pcs resource update redis op start timeout=200s
    fi
    if pcs resource show redis | grep -E "stop.*timeout=120"; then
        pcs resource update redis op stop timeout=200s
    fi
fi

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1635205
if [[ -n $(rpm -q --scripts openvswitch | awk '/postuninstall/,/*/' | grep "systemctl.*try-restart") ]]; then
    echo "Manual upgrade of openvswitch - restart in postun detected"
    mkdir OVS_UPGRADE || true
    pushd OVS_UPGRADE
    echo "Attempting to downloading latest openvswitch with yumdownloader"
    yumdownloader --resolve openvswitch
    echo "Updating openvswitch with nopostun option"
    rpm -U --replacepkgs --nopostun ./*.rpm
    popd
else
    echo "Skipping manual upgrade of openvswitch - no restart in postun detected"
fi

if [[ "$pacemaker_status" == "active" ]] ; then
    echo "Pacemaker running, stopping cluster node and doing full package update"
    node_count=$(pcs status xml | grep -o "<nodes_configured.*/>" | grep -o 'number="[0-9]*"' | grep -o "[0-9]*")
    if [[ "$node_count" == "1" ]] ; then
        echo "Active node count is 1, stopping node with --force"
        pcs cluster stop --force
    else
        pcs cluster stop
    fi
else
    echo "Upgrading openstack-puppet-modules and its dependencies"
    yum -q -y update openstack-puppet-modules
    yum deplist openstack-puppet-modules | awk '/dependency/{print $2}' | xargs yum -q -y update
    echo "Upgrading other packages is handled by config management tooling"
    echo -n "true" > $heat_outputs_path.update_managed_packages
    exit 0
fi

command=${command:-update}
full_command="yum -q -y $command $command_arguments"
echo "Running: $full_command"

result=$($full_command)
return_code=$?
echo "$result"
echo "yum return code: $return_code"

# Writes any changes caused by alterations to os-net-config and bounces the
# interfaces *before* restarting the cluster.
os-net-config -c /etc/os-net-config/config.json -v --detailed-exit-codes
RETVAL=$?
if [[ $RETVAL == 2 ]]; then
    echo "os-net-config: interface configuration files updated successfully"
elif [[ $RETVAL != 0 ]]; then
    echo "ERROR: os-net-config configuration failed"
    exit $RETVAL
fi

if [[ "$pacemaker_status" == "active" ]] ; then
    echo "Starting cluster node"
    pcs cluster start

    hostname=$(hostname -s)
    tstart=$(date +%s)
    while [[ "$(pcs status | grep "^Online" | grep -F -o $hostname)" == "" ]]; do
        sleep 5
        tnow=$(date +%s)
        if (( tnow-tstart > cluster_start_timeout )) ; then
            echo "ERROR $hostname failed to join cluster in $cluster_start_timeout seconds"
            pcs status
            exit 1
        fi
    done

    tstart=$(date +%s)
    while ! clustercheck; do
        sleep 5
        tnow=$(date +%s)
        if (( tnow-tstart > galera_sync_timeout )) ; then
            echo "ERROR galera sync timed out"
            exit 1
        fi
    done

    echo "Waiting for pacemaker cluster to settle"
    if ! timeout -k 10 $cluster_settle_timeout crm_resource --wait; then
        echo "ERROR timed out while waiting for the cluster to settle"
        exit 1
    fi

    pcs status
fi

echo "Finished yum_update.sh on server $deploy_server_id at `date`"

exit $return_code
