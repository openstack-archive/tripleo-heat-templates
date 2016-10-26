#!/bin/bash
#
# This delivers the swift-storage upgrade script to be invoked as part of the tripleo
# major upgrade workflow.
#
set -eu

UPGRADE_SCRIPT=/root/tripleo_upgrade_node.sh

cat > $UPGRADE_SCRIPT << ENDOFCAT
### DO NOT MODIFY THIS FILE
### This file is automatically delivered to the swift-storage nodes as part of the
### tripleo upgrades workflow

set -eu

function systemctl_swift {
    action=\$1
    for S in openstack-swift-account-auditor openstack-swift-account-reaper openstack-swift-account-replicator openstack-swift-account \
             openstack-swift-container-auditor openstack-swift-container-replicator openstack-swift-container-updater openstack-swift-container \
             openstack-swift-object-auditor openstack-swift-object-replicator openstack-swift-object-updater openstack-swift-object; do
                systemctl \$action \$S
    done
}

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

systemctl_swift stop

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y update

systemctl_swift start



ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

