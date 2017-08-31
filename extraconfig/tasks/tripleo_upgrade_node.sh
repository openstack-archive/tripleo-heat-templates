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
if hiera -c /etc/puppet/hiera.yaml service_names | grep nova_compute ; then
   NOVA_COMPUTE="true"
fi
SWIFT_STORAGE=""
if hiera -c /etc/puppet/hiera.yaml service_names | grep swift_storage ; then
   SWIFT_STORAGE="true"
fi

DEBUG="true"
SCRIPT_NAME=$(basename $0)
$(declare -f log_debug)

log_debug "$UPGRADE_SCRIPT has completed - moving onto ansible playbooks"

ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT

