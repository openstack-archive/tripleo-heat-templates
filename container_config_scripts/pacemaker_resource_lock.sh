#!/bin/bash

MAX_RETRIES=10
CIB_ENOTFOUND=105

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

lock_create() {
    local name=$1
    local data=$2
    # cibadmin won't overwrite a key if someone else succeeded to create it concurrently
    cibadmin --sync-call --scope crm_config --create --xml-text "<cluster_property_set id='${name}'><nvpair id='${name}-pair' name='${name}' value='${data}'/></cluster_property_set>" &>/dev/null
    return $?
}

lock_update() {
    local name=$1
    local expected_data=$2
    local new_data=$3
    # we only update the lock we expect to see, so we can't update someone else's lock
    cibadmin --sync-call --scope crm_config --modify --xpath "//cluster_property_set/nvpair[@name='${name}' and @value='${expected_data}']/.." --xml-text "<nvpair id='${name}-pair' name='${name}' value='${new_data}'/>" &>/dev/null
    return $?
}

lock_delete() {
    local name=$1
    local expected_data=$2
    # we only delete the lock we expect to see, so we can't delete someone else's lock
    cibadmin --sync-call --scope crm_config --delete --xpath "//cluster_property_set/nvpair[@name='${name}' and @value='${expected_data}']/.." &>/dev/null
    return $?
}

lock_get() {
    local lockname=$1
    local res
    local rc
    res=$(cibadmin --query --scope crm_config --xpath "//cluster_property_set/nvpair[@name='$lockname']" 2>/dev/null)
    rc=$?
    if [ $rc -eq 0 ]; then
        echo "$res" | sed -n 's/.*value="\([^"]*\)".*/\1/p'
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

# The lock mechanism uses cibadmin's atomic creation so cluster-wide
# state coherency is guaranteed by pacemaker
lock_acquire() {
    local lockname=$1
    local requester=$2
    local ttl=$3
    local rc
    local lock
    local expiry
    local owner

    log "Check whether the lock is already held in the CIB"
    lock=$(lock_get $lockname)
    rc=$?
    if [ $rc -ne 0 ] && [ $rc -ne $CIB_ENOTFOUND ]; then
        log "Could not retrieve info from the CIB"
        return 2
    fi

    if [ -n "$lock" ]; then
        lock_has_expired $lock
        rc=$?
        if [ $rc -eq 0 ]; then
            log "Lock has expired, now available for being held"
        else
            # lock is still held. check whether we're the owner
            owner=$(lock_owner $lock)
            if [ "$owner" = "$requester" ];then
                log "Requester already owns the lock, acquiring attempt will just reconfigure the TTL"
            else
                log "Lock is held by someone else ($owner)"
                return 1
            fi
        fi
    else
        log "Lock is not held yet"
    fi

    # prepare the lock info
    expiry=$(($(date +%s) + $ttl))

    if [ -n "$lock" ]; then
        log "Attempting to update the lock"
        lock_update $lockname "$lock" "$requester:$expiry"
        rc=$?
    else
        log "Attempting to acquire the lock"
        lock_create $lockname "$requester:$expiry"
        rc=$?
    fi

    if [ $rc -eq 0 ]; then
        log "Lock '$lockname' acquired by '$requester', valid until $(date -d @$expiry)"
        return 0
    else
        log "CIB changed, lock cannot be acquired"
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

    log "Check whether the lock is already held in the CIB"
    lock=$(lock_get $lockname)
    rc=$?
    if [ $rc -ne 0 ] && [ $rc -ne $CIB_ENOTFOUND ]; then
        log "Could not retrieve info from the CIB"
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

    lock_delete $lockname "$lock"
    rc=$?

    if [ $rc -eq 0 ]; then
        log "Lock '$lockname' released by '$requester'"
        return 0
    else
        log "CIB deletion error, lock cannot be released"
        return 3
    fi
}


# Retrieve the owner of a lock from the CIB
# this is a read-only operation, so no need to log debug info
lock_get_owner() {
    local lockname=$1
    local rc
    local lock
    local owner

    lock=$(lock_get $lockname)
    rc=$?
    if [ $rc -ne 0 ] && [ $rc -ne $CIB_ENOTFOUND ]; then
        return 2
    fi

    if [ -z "$lock" ]; then
        return 1
    else
        lock_owner $lock
        return 0
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
    if [ -z "$LOCKNAME" ]; then
        error "You must specific a lock name"
    fi
    if [ $ACTION != "--owner" ] && [ $ACTION != "-o" ]; then
        if [ -z "$REQUESTER" ]; then
            error "You must specific a lock requester"
        fi
    fi
fi

case $ACTION in
    --help) usage; exit 0;;
    --acquire|-a) try_action lock_acquire $LOCKNAME $REQUESTER $TTL;;
    --release|-r) try_action lock_release $LOCKNAME $REQUESTER;;
    --acquire-once|-A) lock_acquire $LOCKNAME $REQUESTER $TTL;;
    --owner|-o) lock_get_owner $LOCKNAME;;
    *) error "Invalid action";;
esac
exit $?
