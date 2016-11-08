#!/bin/bash
#
# This delivers the compute upgrade script to be invoked as part of the tripleo
# major upgrade workflow.
#
set -eu

UPGRADE_SCRIPT=/root/tripleo_upgrade_node.sh

cat > $UPGRADE_SCRIPT << ENDOFCAT
### DO NOT MODIFY THIS FILE
### This file is automatically delivered to the compute nodes as part of the
### tripleo upgrades workflow

set -eu

# pin nova to kilo (messaging +-1) for the nova-compute service

crudini  --set /etc/nova/nova.conf upgrade_levels compute $upgrade_level_nova_compute

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1635205
if [[ -n \$(rpm -q --scripts openvswitch | awk '/postuninstall/,/*/' | grep "systemctl.*try-restart") ]]; then
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
yum -y update

# Due to bug#1640177 we need to restart compute agent
echo "Restarting openstack ceilometer agent compute"
systemctl restart openstack-ceilometer-compute

ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

