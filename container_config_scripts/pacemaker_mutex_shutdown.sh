#!/bin/bash

# pacemaker_mutex_shutdown.sh --acquire
# pacemaker_mutex_shutdown.sh --release

set -u

usage() {
    echo "Shutdown a cluster node in a coordinated way across the cluster"
    echo "Usage:"
    echo "   $0 --acquire # prevent other node from shutting down until we hold the lock"
    echo "   $0 --release # release the lock, other node can compete for the shutdown lock"
    echo
}

log() {
    echo "$(date -u): $1"
}

error() {
    echo "$(date -u): $1" 1>&2
    exit 1
}

# Loop until we hold the lock. The lock has a TTL, so we're guaranteed to get it eventually
shutdown_lock_acquire() {
    local lockname=$1
    local requester=$2
    local ttl=$3
    local rc=1
    local current_owner
    local owner_stopped
    local owner_rc

    log "Acquiring the shutdown lock"
    while [ $rc -ne 0 ]; do
        /var/lib/container-config-scripts/pacemaker_resource_lock.sh --acquire-once $lockname $requester $ttl
        rc=$?
        if [ $rc -ne 0 ]; then
            if [ $rc -eq 2 ]; then
                error "Could not acquire the shutdown lock due to unrecoverable error (rc: $rc), bailing out"
            else
                # The lock is held by another node.
                current_owner=$(/var/lib/container-config-scripts/pacemaker_resource_lock.sh --owner $lockname)
                owner_rc=$?
                if [ $owner_rc -eq 2 ]; then
                    error "Could not get the shutdown lock owner due to unrecoverable error (rc: $owner_rc), bailing out"
                fi
                if [ $owner_rc -eq 0 ]; then
                    # If the owner is marked as offline, that means it has shutdown and
                    # we can clean the lock preemptively and try to acquire it.
                    owner_stopped=$(crm_mon -1X | xmllint --xpath 'count(//nodes/node[@name="'${current_owner}'" and @online="false" and @unclean="false"])' -)
                    if [ "${owner_stopped}" = "1" ]; then
                        log "Shutdown lock held by stopped node '${current_owner}', lock can be released"
                        /var/lib/container-config-scripts/pacemaker_resource_lock.sh --release $lockname $current_owner
                        continue
                    fi
                fi
                log "Shutdown lock held by another node (rc: $rc), retrying"
                sleep 10
            fi
        fi
    done
    log "Shutdown lock acquired"
    return 0
}


# Release the lock if we still own it. Not owning it anymore is not fatal
shutdown_lock_release() {
    local lockname=$1
    local requester=$2
    local rc

    log "Releasing the shutdown lock"
    /var/lib/container-config-scripts/pacemaker_resource_lock.sh --release $lockname $requester
    rc=$?
    if [ $rc -ne 0 ]; then
        if [ $rc -gt 1 ]; then
            error "Could not release the shutdown lock due to unrecoverable error (rc: $rc), bailing out"
        else
            log "Shutdown lock no longer held, nothing to do"
        fi
    else
        log "Shutdown lock released"
    fi
    return 0
}


ACTION=$1
if [ -z "$ACTION" ]; then
    error "Action must be specified"
fi

LOCK_NAME=tripleo-shutdown-lock
LOCK_OWNER=$(crm_node -n 2>/dev/null)
rc=$?
if [ $rc -ne 0 ]; then
    if [ $rc -eq 102 ]; then
        log "Cluster is not running locally, no need to aquire the shutdown lock"
        exit 0
    else
        error "Unexpected error while connecting to the cluster (rc: $rc), bailing out"
    fi
fi

# We start with a very high TTL, that long enough to accomodate a cluster stop.
# As soon as the node will get offline, the other competing node will be entitled
# to steal the lock, so they should never wait that long in practice.
LOCK_TTL=600


case $ACTION in
    --help) usage; exit 0;;
    --acquire|-a) shutdown_lock_acquire ${LOCK_NAME} ${LOCK_OWNER} ${LOCK_TTL};;
    --release|-r) shutdown_lock_release ${LOCK_NAME} ${LOCK_OWNER};;
    *) error "Invalid action";;
esac
exit $?
