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
cluster_start_timeout=360
galera_sync_timeout=360

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

if [[ "$pacemaker_status" == "active" ]] ; then
    echo "Checking for and adding missing constraints"

    if ! pcs constraint order show | grep "start openstack-nova-novncproxy-clone then start openstack-nova-api-clone"; then
        pcs constraint order start openstack-nova-novncproxy-clone then openstack-nova-api-clone
    fi

    if ! pcs constraint order show | grep "start rabbitmq-clone then start openstack-keystone-clone"; then
        pcs constraint order start rabbitmq-clone then openstack-keystone-clone
    fi

    if ! pcs constraint order show | grep "promote galera-master then start openstack-keystone-clone"; then
        pcs constraint order promote galera-master then openstack-keystone-clone
    fi

    if ! pcs constraint order show | grep "start haproxy-clone then start openstack-keystone-clone"; then
        pcs constraint order start haproxy-clone then openstack-keystone-clone
    fi

    if ! pcs constraint order show | grep "start memcached-clone then start openstack-keystone-clone"; then
        pcs constraint order start memcached-clone then openstack-keystone-clone
    fi

    if ! pcs constraint order show | grep "promote redis-master then start openstack-ceilometer-central-clone"; then
        pcs constraint order promote redis-master then start openstack-ceilometer-central-clone require-all=false
    fi

    if ! pcs resource defaults | grep "resource-stickiness: INFINITY"; then
        pcs resource defaults resource-stickiness=INFINITY
    fi

    echo "Setting resource start/stop timeouts"

    # timeouts for non-openstack services and special cases
    pcs resource update haproxy op start timeout=100s
    pcs resource update haproxy op stop timeout=100s
    # mongod start timeout is also higher, setting only stop timeout
    pcs resource update mongod op stop timeout=100s
    # rabbit start timeout is already 100s
    pcs resource update rabbitmq op stop timeout=100s
    pcs resource update memcached op start timeout=100s
    pcs resource update memcached op stop timeout=100s
    pcs resource update httpd op start timeout=100s
    pcs resource update httpd op stop timeout=100s
    # neutron-netns-cleanup stop timeout is 300s, setting only start timeout
    pcs resource update neutron-netns-cleanup op start timeout=100s
    # neutron-ovs-cleanup stop timeout is 300s, setting only start timeout
    pcs resource update neutron-ovs-cleanup op start timeout=100s

    # timeouts for openstack services
    pcs resource update neutron-dhcp-agent op start timeout=100s
    pcs resource update neutron-dhcp-agent op stop timeout=100s
    pcs resource update neutron-l3-agent op start timeout=100s
    pcs resource update neutron-l3-agent op stop timeout=100s
    pcs resource update neutron-metadata-agent op start timeout=100s
    pcs resource update neutron-metadata-agent op stop timeout=100s
    pcs resource update neutron-openvswitch-agent op start timeout=100s
    pcs resource update neutron-openvswitch-agent op stop timeout=100s
    pcs resource update neutron-server op start timeout=100s
    pcs resource update neutron-server op stop timeout=100s
    pcs resource update openstack-ceilometer-alarm-evaluator op start timeout=100s
    pcs resource update openstack-ceilometer-alarm-evaluator op stop timeout=100s
    pcs resource update openstack-ceilometer-alarm-notifier op start timeout=100s
    pcs resource update openstack-ceilometer-alarm-notifier op stop timeout=100s
    pcs resource update openstack-ceilometer-api op start timeout=100s
    pcs resource update openstack-ceilometer-api op stop timeout=100s
    pcs resource update openstack-ceilometer-central op start timeout=100s
    pcs resource update openstack-ceilometer-central op stop timeout=100s
    pcs resource update openstack-ceilometer-collector op start timeout=100s
    pcs resource update openstack-ceilometer-collector op stop timeout=100s
    pcs resource update openstack-ceilometer-notification op start timeout=100s
    pcs resource update openstack-ceilometer-notification op stop timeout=100s
    pcs resource update openstack-cinder-api op start timeout=100s
    pcs resource update openstack-cinder-api op stop timeout=100s
    pcs resource update openstack-cinder-scheduler op start timeout=100s
    pcs resource update openstack-cinder-scheduler op stop timeout=100s
    pcs resource update openstack-cinder-volume op start timeout=100s
    pcs resource update openstack-cinder-volume op stop timeout=100s
    pcs resource update openstack-glance-api op start timeout=100s
    pcs resource update openstack-glance-api op stop timeout=100s
    pcs resource update openstack-glance-registry op start timeout=100s
    pcs resource update openstack-glance-registry op stop timeout=100s
    pcs resource update openstack-heat-api op start timeout=100s
    pcs resource update openstack-heat-api op stop timeout=100s
    pcs resource update openstack-heat-api-cfn op start timeout=100s
    pcs resource update openstack-heat-api-cfn op stop timeout=100s
    pcs resource update openstack-heat-api-cloudwatch op start timeout=100s
    pcs resource update openstack-heat-api-cloudwatch op stop timeout=100s
    pcs resource update openstack-heat-engine op start timeout=100s
    pcs resource update openstack-heat-engine op stop timeout=100s
    pcs resource update openstack-keystone op start timeout=100s
    pcs resource update openstack-keystone op stop timeout=100s
    pcs resource update openstack-nova-api op start timeout=100s
    pcs resource update openstack-nova-api op stop timeout=100s
    pcs resource update openstack-nova-conductor op start timeout=100s
    pcs resource update openstack-nova-conductor op stop timeout=100s
    pcs resource update openstack-nova-consoleauth op start timeout=100s
    pcs resource update openstack-nova-consoleauth op stop timeout=100s
    pcs resource update openstack-nova-novncproxy op start timeout=100s
    pcs resource update openstack-nova-novncproxy op stop timeout=100s
    pcs resource update openstack-nova-scheduler op start timeout=100s
    pcs resource update openstack-nova-scheduler op stop timeout=100s

    echo "Pacemaker running, stopping cluster node and doing full package update"
    node_count=$(pcs status xml | grep -o "<nodes_configured.*/>" | grep -o 'number="[0-9]*"' | grep -o "[0-9]*")
    if [[ "$node_count" == "1" ]] ; then
        echo "Active node count is 1, stopping node with --force"
        pcs cluster stop --force
    else
        pcs cluster stop
    fi
else
    echo "Excluding upgrading packages that are handled by config management tooling"
    command_arguments="$command_arguments --skip-broken"
    for exclude in $(cat /var/lib/tripleo/installed-packages/* | sort -u); do
        command_arguments="$command_arguments --exclude $exclude"
    done
fi

command=${command:-update}
full_command="yum -y $command $command_arguments"
echo "Running: $full_command"

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

    tstart=$(date +%s)
    while ! clustercheck; do
        sleep 5
        tnow=$(date +%s)
        if (( tnow-tstart > galera_sync_timeout )) ; then
            echo "ERROR galera sync timed out"
            exit 1
        fi
    done

    pcs status

else
    echo -n "true" > $heat_outputs_path.update_managed_packages
fi

echo "Finished yum_update.sh on server $deploy_server_id at `date`"

exit $return_code
