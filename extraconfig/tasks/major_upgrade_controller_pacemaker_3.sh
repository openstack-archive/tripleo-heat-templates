#!/bin/bash

set -eu

cluster_form_timeout=600
cluster_settle_timeout=1800
galera_sync_timeout=600

if [[ -n $(is_bootstrap_node) ]]; then
    pcs cluster start --all

    tstart=$(date +%s)
    while pcs status 2>&1 | grep -E '(cluster is not currently running)|(OFFLINE:)'; do
        sleep 5
        tnow=$(date +%s)
        if (( tnow-tstart > cluster_form_timeout )) ; then
            echo_error "ERROR: timed out forming the cluster"
            exit 1
        fi
    done

    if ! timeout -k 10 $cluster_settle_timeout crm_resource --wait; then
        echo_error "ERROR: timed out waiting for cluster to finish transition"
        exit 1
    fi

    for vip in $(pcs resource show | grep ocf::heartbeat:IPaddr2 | grep Stopped | awk '{ print $1 }'); do
      pcs resource enable $vip
      check_resource_pacemaker $vip started 60
    done
fi

start_or_enable_service galera
check_resource galera started 600
start_or_enable_service redis
check_resource redis started 600
# We need mongod which is now a systemd service up and running before calling
# ceilometer-dbsync. There is still a race here: mongod might not be up on all nodes
# so ceilometer-dbsync will fail a couple of times before that. As it retries indefinitely
# we should be good.
# Due to LP Bug https://bugs.launchpad.net/tripleo/+bug/1627254 am using systemctl directly atm
systemctl start mongod
check_resource mongod started 600

if [[ -n $(is_bootstrap_node) ]]; then
    tstart=$(date +%s)
    while ! clustercheck; do
        sleep 5
        tnow=$(date +%s)
        if (( tnow-tstart > galera_sync_timeout )) ; then
            echo_error "ERROR galera sync timed out"
            exit 1
        fi
    done

    # Run all the db syncs
    # TODO: check if this can be triggered in puppet and removed from here
    ceilometer-dbsync --config-file=/etc/ceilometer/ceilometer.conf
    cinder-manage db sync
    glance-manage --config-file=/etc/glance/glance-registry.conf db_sync
    heat-manage --config-file /etc/heat/heat.conf db_sync
    keystone-manage db_sync
    neutron-db-manage --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugin.ini upgrade head
    nova-manage db sync
    nova-manage api_db sync
    nova-manage db online_data_migrations
    sahara-db-manage --config-file /etc/sahara/sahara.conf upgrade head
fi
