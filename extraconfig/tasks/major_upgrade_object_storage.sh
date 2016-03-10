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


function systemctl_swift {
    action=\$1
    for S in openstack-swift-account-auditor openstack-swift-account-reaper openstack-swift-account-replicator openstack-swift-account \
             openstack-swift-container-auditor openstack-swift-container-replicator openstack-swift-container-updater openstack-swift-container \
             openstack-swift-object-auditor openstack-swift-object-replicator openstack-swift-object-updater openstack-swift-object; do
                systemctl \$action \$S
    done
}


systemctl_swift stop

yum -y install python-zaqarclient  # needed for os-collect-config
yum -y update

systemctl_swift start



ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

