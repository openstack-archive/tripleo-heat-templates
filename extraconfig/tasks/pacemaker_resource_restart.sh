#!/bin/bash

set -eux

pacemaker_status=$(systemctl is-active pacemaker)

# Run if pacemaker is running, we're the bootstrap node,
# and we're updating the deployment (not creating).
if [ "$pacemaker_status" = "active" -a \
     "$(hiera bootstrap_nodeid)" = "$(facter hostname)" -a \
     "$(hiera stack_action)" = "UPDATE" ]; then

    PCMK_RESOURCES="haproxy-clone redis-master rabbitmq-clone galera-master openstack-cinder-volume openstack-cinder-backup"
    # Ten minutes of timeout to restart each resource, given there are no constraints should be enough
    TIMEOUT=600
    for resource in $PCMK_RESOURCES; do
      if pcs status | grep $resource; then
        pcs resource restart --wait=$TIMEOUT $resource
      fi
    done
fi
