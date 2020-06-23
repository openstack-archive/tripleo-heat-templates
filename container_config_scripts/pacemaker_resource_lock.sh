#!/bin/bash

MAX_RETRIES=10
TMP_CIB=$(mktemp -p /var/lib/pacemaker/cib -t tmpcib.XXXXXXXX)
function finish {
    rm -f $TMP_CIB
}
trap finish EXIT
trap exit INT TERM

usage() {
   echo "Set a global property in the cluster with a validity timestamp."
   echo "Usage:"
   echo "   $0 --acquire <lock_name> <lock_owner> <lock_ttl_in_seconds>"
   echo "   $0 --release <lock_name> <lock_owner>"
   echo
}

log() {
    echo "$(date -u): $1" 1>&2
}

error() {
    echo "$(date -u): $1" 1>&2
    exit 1
}


lock_get() {
    local cib_copy=$1
    local lockname=$2
    local res
    local rc
    res=$(pcs -f $cib_copy property show "$lockname")
    rc=$?
    if [ $rc -eq 0 ]; then
        echo "$res" |  grep -w "$lockname" | cut -d' ' -f3
    fi
    return $rc
}

lock_owner() {
    local lock=$1
    echo "$lock" | cut -d':' -f1
}

lock_has_expired() {
    local lock=$1
    local expiry=$(echo "$lock" | cut -d':' -f2)
    local now=$(date +%s)
    test $now -ge $expiry
}


# Perform a lock action and restart if the CIB has been modified before
# committing the lock action
try_action() {
    local fun=$1
    local lock=$2
    local requester=$3
    local args=${4:-}
    local tries=$MAX_RETRIES
    local rc=1
    if [ "$fun" = "lock_acquire" ] || [ "$fun" = "lock_release" ]; then
        log "Try running $fun"
    else
        return 2
    fi
    while [ $rc -ne 0 ]; do
        $fun $lock $requester $args
        rc=$?
        if [ $rc -eq 0 ]; then
            log "Operation $1 succeeded"
            return 0
        elif [ $rc -eq 3 ]; then
            # rc == 3 -> CIB changed before push
            if [ $tries -eq 0 ]; then
                log "Failed to commit after $MAX_RETRIES retries. Bailing out."
                return 2
            else
                log "Failed to commit. Retrying operation."
                tries=$(($tries - 1))
            fi
        elif [ $rc -eq 2 ]; then
            # rc == 2 -> unrecoverable cib error (e.g. pacemaker down)
            log "Unexpected failure. Bailing out"
            return $rc
        else
            # rc == 1 -> lock error (not owner, lock doesn't exists)
            return $rc
        fi
    done
}

# The lock mechanism uses the CIB's num_updates tag to implement
# a conditional store. Cluster-wide locking is guaranteed by pacemaker
lock_acquire() {
    local lockname=$1
    local requester=$2
    local ttl=$3
    local rc
    local lock
    local expiry
    local owner

    log "Snapshot the current CIB"
    pcs cluster cib > $TMP_CIB
    rc=$?
    if [ $rc -ne 0 ]; then
        log "Could not snapshot the CIB"
        return 2
    fi

    log "Check whether the lock is already held in the CIB"
    lock=$(lock_get $TMP_CIB $lockname)
    rc=$?
    if [ $rc -ne 0 ]; then
        log "Could not retrieve info from snapshot CIB"
        return 2
    fi

    if [ -n "$lock" ]; then
        log "Lock exists, check whether it has expired"
        lock_has_expired $lock
        rc=$?
        if [ $rc -eq 0 ]; then
            log "Lock has expired, now available for being held"
        else
            # lock is still held. check whether we're the owner
            owner=$(lock_owner $lock)
            if [ "$owner" = "$requester" ];then
                log "Already own the lock, acquiring attempt will just reconfigure the TTL"
            else
                log "Lock is held by someone else ($owner)"
                return 1
            fi
        fi
    else
        log "Lock is not held yet"
    fi

    log "Prepare the snapshot CIB to acquire the lock"
    expiry=$(($(date +%s) + $ttl))
    pcs -f $TMP_CIB property set "$lockname"="$requester:$expiry" --force

    # Store Conditional: only works if no update have been pushed in the meantime"
    log "Try to push the CIB to signal lock is acquired"
    pcs cluster cib-push $TMP_CIB
    rc=$?

    if [ $rc -eq 0 ]; then
        log "Lock '$lockname' acquired by '$requester', valid until $(date -d @$expiry)"
        return 0
    else
        log "CIB changed since snapshot, lock cannot be acquired"
        return 3
    fi
}


# The lock mechanism uses the CIB's num_updates tag to implement
# a conditional store. Cluster-wide locking is guaranteed by pacemaker
lock_release() {
    local lockname=$1
    local requester=$2
    local rc
    local lock
    local owner

    log "Snapshot the current CIB"
    pcs cluster cib > $TMP_CIB
    rc=$?
    if [ $rc -ne 0 ]; then
        log "Could not snapshot the CIB"
        return 2
    fi

    log "Check whether the lock is already held in the CIB"
    lock=$(lock_get $TMP_CIB $lockname)
    rc=$?
    if [ $rc -ne 0 ]; then
        log "Could not retrieve info from snapshot CIB"
        return 2
    fi

    if [ -z "$lock" ]; then
        log "Lock doesn't exist. Nothing to release"
        return 0
    else
        log "Lock exists, check whether we're the owner"
        owner=$(lock_owner $lock)
        if [ "$owner" != "$requester" ];then
            log "Lock is held by someone else ($owner), will not unlock"
            return 1
        fi
    fi

    log "Prepare the snapshot CIB to release the lock"
    pcs -f $TMP_CIB property set "$lockname"=""

    # Store Conditional: only works if no update have been pushed in the meantime"
    log "Try to push the CIB to signal lock is released"
    pcs cluster cib-push $TMP_CIB
    rc=$?

    if [ $rc -eq 0 ]; then
        log "Lock '$lockname' released by '$requester'"
        return 0
    else
        log "CIB changed since snapshot, lock cannot be released"
        return 3
    fi
}


ACTION=$1
LOCKNAME=$2
REQUESTER=$3
TTL=${4:-60}

if [ -z "$ACTION" ]; then
    error "Action must be specified"
fi

if [ $ACTION != "--help" ]; then
    if [ -z "$LOCKNAME" ] || [ -z "$REQUESTER" ]; then
        error "You must specific a lock name and a requester"
    fi
fi

case $ACTION in
    --help) usage; exit 0;;
    --acquire|-a) try_action lock_acquire $LOCKNAME $REQUESTER $TTL;;
    --release|-r) try_action lock_release $LOCKNAME $REQUESTER;;
    *) error "Invalid action";;
esac
exit $?
