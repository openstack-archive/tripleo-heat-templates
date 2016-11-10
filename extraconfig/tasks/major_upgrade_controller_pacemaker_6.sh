#!/bin/bash

set -eu

# We need to start the systemd services we explicitely stopped at step _1.sh
# FIXME: Should we let puppet during the convergence step do the service enabling or
# should we add it here?
services=$(services_to_migrate)
if [[ ${keep_sahara_services_on_upgrade} =~ [Ff]alse ]] ; then
    services=${services%%openstack-sahara*}
fi
for service in $services; do
    manage_systemd_service start "${service%%-clone}"
    check_resource_systemd "${service%%-clone}" started 600
done
