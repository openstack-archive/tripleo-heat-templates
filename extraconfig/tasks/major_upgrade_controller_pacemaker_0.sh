#!/bin/bash

set -eu

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
    # We create this empty file if stonith was set to true so we can reenable stonith in step2
    rm -f /var/tmp/stonith-true
    if [ $STONITH_STATE == "true" ]; then
        touch /var/tmp/stonith-true
    fi
    pcs property set stonith-enabled=false
fi

# Before migration and service stopping we make sure that the external
# bridge is set to standalone in ovs.  This is because we don't do a
# rolling upgrade, but we don't want the floating ip network to be cut
# off.
for br in $(get_all_bridges); do
    # It we be set to whatever is needed at the end of the upgrade by
    # ovs-agent processes.
    ovs-vsctl set-fail-mode ${br} standalone
done

# Make sure openvswitch *cleanup* does not happen.
deactivate_cleanup_services
