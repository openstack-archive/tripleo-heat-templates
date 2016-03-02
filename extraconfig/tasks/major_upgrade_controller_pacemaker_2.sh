#!/bin/bash

set -eu

cluster_form_timeout=600
cluster_settle_timeout=600
galera_sync_timeout=600

if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
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

    pcs resource enable galera
    check_resource galera started 600
    pcs resource enable mongod
    check_resource mongod started 600

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

    pcs resource enable memcached
    check_resource memcached started 600
    pcs resource enable rabbitmq
    check_resource rabbitmq started 600
    pcs resource enable redis
    check_resource redis started 600
    if pcs status | grep openstack-keystone; then
        pcs resource enable openstack-keystone
        check_resource openstack-keystone started 1800
    fi
    pcs resource enable httpd
    check_resource httpd started 1800
fi

# Swift isn't controled by heat
systemctl_swift start
