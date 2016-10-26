#!/bin/bash
#
# This delivers the ceph-storage upgrade script to be invoked as part of the tripleo
# major upgrade workflow.
#
set -eu

UPGRADE_SCRIPT=/root/tripleo_upgrade_node.sh

cat > $UPGRADE_SCRIPT << ENDOFCAT
### DO NOT MODIFY THIS FILE
### This file is automatically delivered to the ceph-storage nodes as part of the
### tripleo upgrades workflow


function systemctl_ceph {
    action=\$1
    systemctl \$action ceph
}

# "so that mirrors aren't rebalanced as if the OSD died" - gfidente
ceph osd set noout

systemctl_ceph stop

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
systemctl_ceph start

ceph osd unset noout

ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

