#!/bin/bash

set -eu

start_or_enable_service rabbitmq
check_resource rabbitmq started 600
start_or_enable_service redis
check_resource redis started 600
start_or_enable_service openstack-cinder-volume
check_resource openstack-cinder-volume started 600


# Swift isn't controled by pacemaker
systemctl_swift start

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
