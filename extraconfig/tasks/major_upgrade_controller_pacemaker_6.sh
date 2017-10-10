#!/bin/bash

set -eu

# We need to start the systemd services we explicitely stopped at step _0.sh
# We add the enablement of the systemd services here because if a node gets rebooted
# before the convergence step for whatever reason the migrated services will
# not be enabled and we potentially have a bigger disruption.
services=$(services_to_migrate)
if [[ ${keep_sahara_services_on_upgrade} =~ [Ff]alse ]] ; then
    services=${services%%openstack-sahara*}
fi

for service in $services; do
    if [[ ${service%%-clone} =~ .*-cleanup ]]; then
        # we don't want to start {netns,ovs}-cleanup
        log_debug "Skipping ${service}"
        continue
    fi

    manage_systemd_service start "${service%%-clone}"
    manage_systemd_service enable "${service%%-clone}"
    check_resource_systemd "${service%%-clone}" started 600
done
