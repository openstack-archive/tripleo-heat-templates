#!/bin/bash

set -eux

# Run if pacemaker is running, we're the bootstrap node,
# and we're updating the deployment (not creating).

RESTART_FOLDER="/var/lib/tripleo/pacemaker-restarts"

if [[ -d "$RESTART_FOLDER" && -n $(pcmk_running) && -n $(is_bootstrap_node) ]]; then

    TIMEOUT=600
    PCS_STATUS_OUTPUT="$(pcs status)"
    SERVICES_TO_RESTART="$(ls $RESTART_FOLDER)"

    for service in $SERVICES_TO_RESTART; do
        if ! echo "$PCS_STATUS_OUTPUT" | grep $service; then
            echo "Service $service not found as a pacemaker resource, cannot restart it."
            exit 1
        fi
    done

    for service in $SERVICES_TO_RESTART; do
        echo "Restarting $service..."
        pcs resource restart --wait=$TIMEOUT $service
        rm -f "$RESTART_FOLDER"/$service
    done

fi

if [ $(systemctl is-active haproxy) = "active" ]; then
    systemctl reload haproxy
fi
