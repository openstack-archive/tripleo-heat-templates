#!/bin/bash

# pacemaker_mutex_restart_bundle.sh --lock mysql galera galera-bundle Master _
# pacemaker_mutex_restart_bundle.sh --lock ovn_dbs ovndb_servers ovn-dbs-bundle Slave Master

set -u

usage() {
    echo "Restart a clustered resource in a coordinated way across the cluster"
    echo "Usage:"
    echo "   $0 --lock <tripleo-service> <pcmk-resource> <pcmk-bundle> <target-state-local> <target-state-cluster>"
    echo
}

log() {
    echo "$(date -u): $1"
}

error() {
    echo "$(date -u): $1" 1>&2
    exit 1
}

ACTION=$1
case $ACTION in
    --help) usage; exit 0;;
    --lock) ;;
    *) error "Unknown action '$ACTION'";;
esac

TRIPLEO_SERVICE=$2
LOCK_NAME=${TRIPLEO_SERVICE}-restart-lock
LOCK_OWNER=$(crm_node -n 2>/dev/null)
rc=$?
if [ $rc -ne 0 ]; then
    if [ $rc -eq 102 ]; then
        log "Cluster is not running locally, no need to restart resource $TRIPLEO_SERVICE"
        exit 0
    else
        error "Unexpected error while connecting to the cluster (rc: $rc), bailing out"
    fi
fi

RESOURCE_NAME=$3
BUNDLE_NAME=$4
WAIT_TARGET_LOCAL=$5
WAIT_TARGET_ANYWHERE=${6:-_}

# The lock TTL should accomodate for the resource start/promote timeout
if [ "$RESOURCE_NAME" != "$BUNDLE_NAME" ]; then
    if [ "$WAIT_TARGET_LOCAL" = "Master" ] || [ "$WAIT_TARGET_ANYWHERE" = "Master" ]; then
        rsc_op="promote"
    else
        rsc_op="start"
    fi
    # <op id="galera-promote-interval-0s" interval="0s" name="promote" on-fail="block" timeout="300s"/>
    PCMK_TTL=$(cibadmin -Q | xmllint -xpath "string(//primitive[@id='${RESOURCE_NAME}']/operations/op[@name='${rsc_op}']/@timeout)" - | sed 's/s$//')
    LOCK_TTL=$((PCMK_TTL + 30))
else
    # The podman RA's default start timeout
    LOCK_TTL=90
fi

log "Acquire a ${LOCK_TTL}s restart lock for service $TRIPLEO_SERVICE before restarting it"
# Loop until we hold the lock. The lock has a TTL, so we're guaranteed to get it eventually
rc=1
while [ $rc -ne 0 ]; do
    /var/lib/container-config-scripts/pacemaker_resource_lock.sh --acquire $LOCK_NAME $LOCK_OWNER $LOCK_TTL
    rc=$?
    if [ $rc != 0 ]; then
        if [ $rc -gt 1 ]; then
            error "Could not acquire lock due to unrecoverable error (rc: $rc), bailing out"
        else
            log "Could not acquire lock, retrying"
            sleep 10
        fi
    fi
done

log "Restart the service $TRIPLEO_SERVICE locally"
# Reuse the local restart script in t-h-t (driven by env var TRIPLEO_MINOR_UPDATE)
TRIPLEO_MINOR_UPDATE=true /var/lib/container-config-scripts/pacemaker_restart_bundle.sh $TRIPLEO_SERVICE $RESOURCE_NAME $BUNDLE_NAME $WAIT_TARGET_LOCAL $WAIT_TARGET_ANYWHERE

# If we reached this point, always try to release the lock
log "Release the restart lock for service $TRIPLEO_SERVICE"
/var/lib/container-config-scripts/pacemaker_resource_lock.sh --release $LOCK_NAME $LOCK_OWNER
rc=$?
if [ $rc -ne 0 ] && [ $rc -ne 1 ]; then
    error "Could not release held lock (rc: $rc)"
fi
