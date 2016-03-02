#!/bin/bash

set -eu

cluster_sync_timeout=600

if pcs status 2>&1 | grep -E '(cluster is not currently running)|(OFFLINE:)'; then
    echo_error "ERROR: upgrade cannot start with some cluster nodes being offline"
    exit 1
fi

if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
    pcs resource disable httpd
    check_resource httpd stopped 1800
    if pcs status | grep openstack-keystone; then
        pcs resource disable openstack-keystone
        check_resource openstack-keystone stopped 1800
    fi
    pcs resource disable redis
    check_resource redis stopped 600
    pcs resource disable mongod
    check_resource mongod stopped 600
    pcs resource disable rabbitmq
    check_resource rabbitmq stopped 600
    pcs resource disable memcached
    check_resource memcached stopped 600
    pcs resource disable galera
    check_resource galera stopped 600
    pcs cluster stop --all
fi

# Swift isn't controled by pacemaker
systemctl_swift stop

tstart=$(date +%s)
while systemctl is-active pacemaker; do
    sleep 5
    tnow=$(date +%s)
    if (( tnow-tstart > cluster_sync_timeout )) ; then
        echo_error "ERROR: cluster shutdown timed out"
        exit 1
    fi
done

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y -q update

# Pin messages sent to compute nodes to kilo, these will be upgraded later
crudini  --set /etc/nova/nova.conf upgrade_levels compute "$upgrade_level_nova_compute"
# https://bugzilla.redhat.com/show_bug.cgi?id=1284047
# Change-Id: Ib3f6c12ff5471e1f017f28b16b1e6496a4a4b435
crudini  --set /etc/ceilometer/ceilometer.conf DEFAULT rpc_backend rabbit
# https://bugzilla.redhat.com/show_bug.cgi?id=1284058
# Ifd1861e3df46fad0e44ff9b5cbd58711bbc87c97 Swift Ceilometer middleware no longer exists
crudini --set /etc/swift/proxy-server.conf pipeline:main pipeline "catch_errors healthcheck cache ratelimit tempurl formpost authtoken keystone staticweb proxy-logging proxy-server"
