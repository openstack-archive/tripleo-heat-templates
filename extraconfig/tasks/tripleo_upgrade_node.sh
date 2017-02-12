#!/bin/bash
#
# This delivers the operator driven upgrade script to be invoked as part of
# the tripleo major upgrade workflow. The utility 'upgrade-non-controller.sh'
# is used from the undercloud to invoke the /root/tripleo_upgrade_node.sh
#
set -eu

UPGRADE_SCRIPT=/root/tripleo_upgrade_node.sh

cat > $UPGRADE_SCRIPT << ENDOFCAT
### DO NOT MODIFY THIS FILE
### This file is automatically delivered to those nodes where the
### disable_upgrade_deployment flag is set in roles_data.yaml.

set -eu
NOVA_COMPUTE=""
if systemctl show 'openstack-nova-compute' --property ActiveState | grep '\bactive\b'; then
   NOVA_COMPUTE="true"
fi

DEBUG="true"
SCRIPT_NAME=$(basename $0)
$(declare -f log_debug)
$(declare -f manage_systemd_service)
$(declare -f systemctl_swift)

# pin nova messaging +-1 for the nova-compute service
if [[ -n \$NOVA_COMPUTE ]]; then
    crudini  --set /etc/nova/nova.conf upgrade_levels compute auto
fi

$(declare -f special_case_ovs_upgrade_if_needed)
special_case_ovs_upgrade_if_needed

yum -y install python-zaqarclient  # needed for os-collect-config
systemctl_swift stop
yum -y update
systemctl_swift start

# Due to bug#1640177 we need to restart compute agent
if [[ -n \$NOVA_COMPUTE ]]; then
    echo "Restarting openstack ceilometer agent compute"
    systemctl restart openstack-ceilometer-compute
fi

# Apply puppet manifest to converge just right after the \$ROLE upgrade
puppet apply /root/${ROLE}_puppet_config.pp

ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

