#!/bin/bash

set -eu

cluster_sync_timeout=1800

check_cluster
check_pcsd
if [[ -n $(is_bootstrap_node) ]]; then
    check_clean_cluster
fi
check_python_rpm
check_galera_root_password
check_disk_for_mysql_dump

# M/N Upgrade only: By default RHEL/Centos has an /etc/sysconfig/iptables file which
# allows ssh and icmp only (INPUT table). During the install of OSP9/Mitaka
# usually the live iptables rules are not the ones in /etc/sysconfig/iptables but
# they are completely open (ACCEPT)
# Now when we run the convergence step while migrating to Newton we enable the firewall
# by default and this will actually first load the rules from /etc/sysconfig/iptables
# and only afterwards, it will start adding all the rules permitting openstack traffic.
# This causes an outage of roughly 1 minute in our env, which disrupts the cluster.
# Let's simply move the existing file out of the way, it will be recreated by
# puppet in newton with the proper firewall rules anyway
if [ ! -f /etc/sysconfig/iptables.m-n-upgrade ]; then
    mv /etc/sysconfig/iptables /etc/sysconfig/iptables.m-n-upgrade || /bin/true
fi

# We want to disable fencing during the cluster --stop as it might fence
# nodes where a service fails to stop, which could be fatal during an upgrade
# procedure. So we remember the stonith state. If it was enabled we reenable it
# at the end of this script
if [[ -n $(is_bootstrap_node) ]]; then
    STONITH_STATE=$(pcs property show stonith-enabled | grep "stonith-enabled" | awk '{ print $2 }')
    pcs property set stonith-enabled=false
fi

# Migrate to HA NG
if [[ -n $(is_bootstrap_node) ]]; then
    migrate_full_to_ng_ha
fi

# After migrating the cluster to HA-NG the services not under pacemaker's control
# are still up and running. We need to stop them explicitely otherwise during the yum
# upgrade the rpm %post sections will try to do a systemctl try-restart <service>, which
# is going to take a long time because rabbit is down. By having the service stopped
# systemctl try-restart is a noop

for service in $(services_to_migrate); do
    manage_systemd_service stop "${service%%-clone}"
    # So the reason for not reusing check_resource_systemd is that
    # I have observed systemctl is-active returning unknown with at least
    # one service that was stopped (See LP 1627254)
    timeout=600
    tstart=$(date +%s)
    tend=$(( $tstart + $timeout ))
    check_interval=3
    while (( $(date +%s) < $tend )); do
      if [[ "$(systemctl is-active ${service%%-clone})" = "active" ]]; then
        echo "$service still active, sleeping $check_interval seconds."
        sleep $check_interval
      else
        # we do not care if it is inactive, unknown or failed as long as it is
        # not running
        break
      fi

    done
done

# In case the mysql package is updated, the database on disk must be
# upgraded as well. This typically needs to happen during major
# version upgrades (e.g. 5.5 -> 5.6, 5.5 -> 10.1...)
#
# Because in-place upgrades are not supported across 2+ major versions
# (e.g. 5.5 -> 10.1), we rely on logical upgrades via dump/restore cycle
# https://bugzilla.redhat.com/show_bug.cgi?id=1341968
#
# The default is to determine automatically if upgrade is needed based
# on mysql package versionning, but this can be overriden manually
# to support specific upgrade scenario

if [[ -n $(is_bootstrap_node) ]]; then
    if [ $DO_MYSQL_UPGRADE -eq 1 ]; then
        mysqldump $backup_flags > "$MYSQL_BACKUP_DIR/openstack_database.sql"
        cp -rdp /etc/my.cnf* "$MYSQL_BACKUP_DIR"
    fi

    pcs resource disable redis
    check_resource redis stopped 600
    pcs resource disable rabbitmq
    check_resource rabbitmq stopped 600
    pcs resource disable galera
    check_resource galera stopped 600
    pcs resource disable openstack-cinder-volume
    check_resource openstack-cinder-volume stopped 600
    # Disable all VIPs before stopping the cluster, so that pcs doesn't use one as a source address:
    #   https://bugzilla.redhat.com/show_bug.cgi?id=1330688
    for vip in $(pcs resource show | grep ocf::heartbeat:IPaddr2 | grep Started | awk '{ print $1 }'); do
      pcs resource disable $vip
      check_resource $vip stopped 60
    done
    pcs cluster stop --all
fi


# Swift isn't controlled by pacemaker
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

# The reason we do an sql dump *and* we move the old dir out of
# the way is because it gives us an extra level of safety in case
# something goes wrong during the upgrade. Once the restore is
# successful we go ahead and remove it. If the directory exists
# we bail out as it means the upgrade process had issues in the last
# run.
if [ $DO_MYSQL_UPGRADE -eq 1 ]; then
    if [ -d $MYSQL_TEMP_UPGRADE_BACKUP_DIR ]; then
        echo_error "ERROR: mysql backup dir already exist"
        exit 1
    fi
    mv /var/lib/mysql $MYSQL_TEMP_UPGRADE_BACKUP_DIR
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

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y -q update

# We need to ensure at least those two configuration settings, otherwise
# mariadb 10.1+ won't activate galera replication.
# wsrep_cluster_address must only be set though, its value does not
# matter because it's overriden by the galera resource agent.
cat >> /etc/my.cnf.d/galera.cnf <<EOF
[mysqld]
wsrep_on = ON
wsrep_cluster_address = gcomm://localhost
EOF

if [ $DO_MYSQL_UPGRADE -eq 1 ]; then
    # Scripts run via heat have no HOME variable set and this confuses
    # mysqladmin
    export HOME=/root

    mkdir /var/lib/mysql || /bin/true
    chown mysql:mysql /var/lib/mysql
    chmod 0755 /var/lib/mysql
    restorecon -R /var/lib/mysql/
    mysql_install_db --datadir=/var/lib/mysql --user=mysql
    chown -R mysql:mysql /var/lib/mysql/

    if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
        mysqld_safe --wsrep-new-cluster &
        # We have a populated /root/.my.cnf with root/password here so
        # we need to temporarily rename it because the newly created
        # db is empty and no root password is set
        mv /root/.my.cnf /root/.my.cnf.temporary
        timeout 60 sh -c 'while ! mysql -e "" &> /dev/null; do sleep 1; done'
        mysql -u root < "$MYSQL_BACKUP_DIR/openstack_database.sql"
        mv /root/.my.cnf.temporary /root/.my.cnf
        mysqladmin -u root shutdown
        # The import was successful so we may remove the folder
        rm -r "$MYSQL_BACKUP_DIR"
    fi
fi

# If we reached here without error we can safely blow away the origin
# mysql dir from every controller

# TODO: What if the upgrade fails on the bootstrap node, but not on
# this controller.  Data may be lost.
if [ $DO_MYSQL_UPGRADE -eq 1 ]; then
    rm -r $MYSQL_TEMP_UPGRADE_BACKUP_DIR
fi

# Let's reset the stonith back to true if it was true, before starting the cluster
if [[ -n $(is_bootstrap_node) ]]; then
    if [ $STONITH_STATE == "true" ]; then
        pcs -f /var/lib/pacemaker/cib/cib.xml property set stonith-enabled=true
    fi
fi

# Pin messages sent to compute nodes to kilo, these will be upgraded later
crudini  --set /etc/nova/nova.conf upgrade_levels compute "$upgrade_level_nova_compute"
# https://bugzilla.redhat.com/show_bug.cgi?id=1284047
# Change-Id: Ib3f6c12ff5471e1f017f28b16b1e6496a4a4b435
crudini  --set /etc/ceilometer/ceilometer.conf DEFAULT rpc_backend rabbit
# https://bugzilla.redhat.com/show_bug.cgi?id=1284058
# Ifd1861e3df46fad0e44ff9b5cbd58711bbc87c97 Swift Ceilometer middleware no longer exists
crudini --set /etc/swift/proxy-server.conf pipeline:main pipeline "catch_errors healthcheck cache ratelimit tempurl formpost authtoken keystone staticweb proxy-logging proxy-server"
# LP: 1615035, required only for M/N upgrade.
crudini --set /etc/nova/nova.conf DEFAULT scheduler_host_manager host_manager
# LP: 1627450, required only for M/N upgrade
crudini --set /etc/nova/nova.conf DEFAULT scheduler_driver filter_scheduler

crudini --set /etc/sahara/sahara.conf DEFAULT plugins ambari,cdh,mapr,vanilla,spark,storm
