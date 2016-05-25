#!/bin/bash

set -eux

# Run if pacemaker is running, we're the bootstrap node,
# and we're updating the deployment (not creating).
if [[ -n $(pcmk_running) && -n $(is_bootstrap_node) ]]; then

    TIMEOUT=600
    SERVICES_TO_RESTART="$(ls /var/lib/tripleo/pacemaker-restarts)"
    PCS_STATUS_OUTPUT="$(pcs status)"

    for service in $SERVICES_TO_RESTART; do
        if ! echo "$PCS_STATUS_OUTPUT" | grep $service; then
            echo "Service $service not found as a pacemaker resource, cannot restart it."
            exit 1
        fi
    done

    for service in $SERVICES_TO_RESTART; do
        echo "Restarting $service..."
        pcs resource restart --wait=$TIMEOUT $service
        rm -f /var/lib/tripleo/pacemaker-restarts/$service
    done
fi
