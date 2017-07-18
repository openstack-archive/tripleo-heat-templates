#!/bin/bash

# A heat-config-script which runs yum update during a stack-update.
# Inputs:
#   deploy_action - yum will only be run if this is UPDATE
#   update_identifier - yum will only run for previously unused values of update_identifier
#   command - yum sub-command to run, defaults to "update"
#   command_arguments - yum command arguments, defaults to ""

echo "Started yum_update.sh on server $deploy_server_id at `date`"
echo -n "false" > $heat_outputs_path.update_managed_packages

if [ -f /.dockerenv ]; then
    echo "Not running due to running inside a container"
    exit 0
fi

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

pacemaker_status=""
# We include word boundaries in order to not match pacemaker_remote
if hiera -c /etc/puppet/hiera.yaml service_names | grep -q '\bpacemaker\b'; then
    pacemaker_status=$(systemctl is-active pacemaker)
fi

# (NB: when backporting this s/pacemaker_short_bootstrap_node_name/bootstrap_nodeid)
# This runs before the yum_update so we are guaranteed to run it even in the absence
# of packages to update (the check for -z "$update_identifier" guarantees that this
# is run only on overcloud stack update -i)
if [[ "$pacemaker_status" == "active" && \
        "$(hiera -c /etc/puppet/hiera.yaml pacemaker_short_bootstrap_node_name | tr '[:upper:]' '[:lower:]')" == "$(facter hostname | tr '[:upper:]' '[:lower:]')" ]] ; then \
    # OCF scripts don't cope with -eu
    echo "Verifying if we need to fix up any IPv6 VIPs"
    set +eu
    fixup_wrong_ipv6_vip
    ret=$?
    set -eu
    if [ $ret -ne 0 ]; then
        echo "Fixing up IPv6 VIPs failed. Stopping here. (See https://bugs.launchpad.net/tripleo/+bug/1686357 for more info)"
        exit 1
    fi
fi

command_arguments=${command_arguments:-}

# Always ensure yum has full cache
yum makecache || echo "Yum makecache failed. This can cause failure later on."

# yum check-update exits 100 if updates are available
set +e
check_update=$(yum check-update 2>&1)
check_update_exit=$?
set -e

if [[ "$check_update_exit" == "1" ]]; then
    echo "Failed to check for package updates"
    echo "$check_update"
    exit 1
elif [[ "$check_update_exit" != "100" ]]; then
    echo "No packages require updating"
    exit 0
fi

# special case https://bugs.launchpad.net/tripleo/+bug/1635205 +bug/1669714
special_case_ovs_upgrade_if_needed

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
    check_for_yum_lock
    yum -q -y update openstack-puppet-modules
    yum deplist openstack-puppet-modules | awk '/dependency/{print $2}' | xargs yum -q -y update
    echo "Upgrading other packages is handled by config management tooling"
    echo -n "true" > $heat_outputs_path.update_managed_packages
    exit 0
fi

command=${command:-update}
full_command="yum -q -y $command $command_arguments"

echo "Running: $full_command"
check_for_yum_lock
result=$($full_command)
return_code=$?
echo "$result"
echo "yum return code: $return_code"

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

    RETVAL=$( pcs resource show galera-master | grep wsrep_cluster_address | grep -q `crm_node -n` ; echo $? )

    if [[ $RETVAL -eq 0 && -e /etc/sysconfig/clustercheck ]]; then
        tstart=$(date +%s)
        while ! clustercheck; do
            sleep 5
            tnow=$(date +%s)
            if (( tnow-tstart > galera_sync_timeout )) ; then
                echo "ERROR galera sync timed out"
                exit 1
            fi
        done
    fi

    echo "Waiting for pacemaker cluster to settle"
    if ! timeout -k 10 $cluster_settle_timeout crm_resource --wait; then
        echo "ERROR timed out while waiting for the cluster to settle"
        exit 1
    fi

    pcs status
fi


echo "Finished yum_update.sh on server $deploy_server_id at `date` with return code: $return_code"

exit $return_code
