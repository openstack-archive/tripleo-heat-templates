#!/bin/bash

# ----
# Wait for an OCF resource or a bundle to be restarted
# ----
# e.g.:
# M/S OCF:      $0 galera galera-bundle Master
# clone OCF:    $0 rabbitmq rabbitmq-bundle Started
# A/P M/S OCF:  $0 redis redis-bundle Slave Master
# A/P bundle:   $0 openstack-cinder-volume openstack-cinder-volume _ Started
# clone bundle: $0 haproxy-bundle haproxy-bundle Started

# design note 1:
#  - this script is called during a minor update; it is called
#    once per node that hosts a service replica.
#  - the purpose of this script is to ensure that restarting the
#    service replica locally won't disrupt the service availability
#    for the end user. To reach that goal, the script waits until the
#    service is restarted locally or globallu and reaches a given
#    target state (i.e. Started, Slave or Master).
# design note 2:
#   - we don't want to track restart error: our only job is to ensure
#     service restart synchronization, not service health.
#   - In particular, we don't want to error out in case the resource
#     cannot be restarted locally, because that would make the minor
#     update fail, even if potentially other replicas still provide
#     the service.
# design note 3:
#   - we can bail out early if we determine that the resource can't
#     be restarted automatically by pacemaker (e.g. its "blocked",
#     unmanaged or disabled).

log() {
    local msg=$1
    echo "$(date -u): $1"
}

usage() {
    echo 2>&1 "Usage: $0 NAME BUNDLE_NAME ROLE_LOCAL [ROLE_ANYWHERE] [HOST] [TIMEOUT]"
    exit 1
}


#
# Utility functions to detect stuck resources
#

bundle_failures_locally() {
    local engine=$BUNDLE_CONTAINER_ENGINE
    local replicas=$BUNDLE_REPLICAS
    local last=$(($replicas - 1))
    local replica_name
    for i in $(seq 0 $last); do
	replica_name=${BUNDLE_NAME}-${engine}-${i}
	crm_failcount -q -G -r $replica_name -N $HOST
    done
}

bundle_failures_globally() {
    local engine=$BUNDLE_CONTAINER_ENGINE
    local replicas=$BUNDLE_REPLICAS
    local last=$(($replicas - 1))
    for i in $(seq 0 $last); do
	crm_failcount -q -G -r ${BUNDLE_NAME}-${engine}-${i}
    done
}

bundle_running_globally() {
    local engine=$BUNDLE_CONTAINER_ENGINE
    # return the number of running bundles replica, i.e. the number of
    # docker/podman resource replicas currently running in the cluster
    crm_mon --as-xml | xmllint --xpath "count(//resources/bundle[@id='${BUNDLE_NAME}']/replica/resource[@resource_agent='ocf::heartbeat:${engine}']/node)" -
}

ocf_failures_globally() {
    local replicas=$BUNDLE_REPLICAS
    local last=$(($replicas - 1))
    local bundle_node
    for i in $(seq 0 $last); do
	bundle_node=${BUNDLE_NAME}-${i}
	crm_failcount -q -G -r $NAME -N $bundle_node
    done
}

did_resource_failed_locally() {
    local failures
    local running
    local remotehost
    if [ "${NAME}" != "${BUNDLE_NAME}" ]; then
	# if we're dealing with an ocf resource, it is running on a
	# pacemaker_remote rather that on the real host, and the
	# failcounts are thus associated to the pcmk remote. Replace
	# the host's name with the pcmk remote's name.
	remotehost=$(crm_mon --as-xml | xmllint --xpath "string(//resources/bundle[@id='${BUNDLE_NAME}']/replica/resource/node[@name='${HOST}']/../../resource[@resource_agent='ocf::pacemaker:remote']/@id)" -)
	if [ -n "${remotehost}" ]; then
	    crm_failcount -q -G -r $NAME -N $remotehost | grep -q -w INFINITY
	    return $?
	fi
	# If no pcmk remote is currently running, the failcount from
	# the ocf resource is useless, compute the failcount from the
	# bundle case instead (computed below).
    fi

    # for bundles, pacemaker can run any bundle replica locally
    # (e.g. galera-bundle-docker-{0,1,2}), and a failure happens when
    # there are no more replica to try.
    # That is, when _at least_ one replica failed locally, and all the
    # others either failed or are currently running elsewhere.
    failures=$(bundle_failures_locally $HOST | grep -c -w INFINITY)
    running=$(bundle_running_globally)
    test $failures -gt 0 && \
    test $(( $failures + $running )) -ge $BUNDLE_REPLICAS
}

did_resource_failed_globally() {
    local remotecount
    local failures
    if [ "${NAME}" != "${BUNDLE_NAME}" ]; then
	# we check the state of an ocf resource only if the
	# pcmkremotes are started
	remotecount=$(crm_mon --as-xml | xmllint --xpath "count(//resources/bundle[@id='${BUNDLE_NAME}']/replica/resource[@resource_agent='ocf::pacemaker:remote']/node)" -)
	if [ "${remotecount}" = "0" ]; then
	    # no pcmkremote is running, so check the bundle state
	    # instead of checking the ocf resource
	    # bundle failed if all ${BUNDLE_REPLICAS} replicas failed
	    failures=$(bundle_failures_globally | grep -c -w INFINITY)
	    test $failures -eq $BUNDLE_REPLICAS
	else
	    # ocf resource failed if it failed to start on
	    # all $BUNDLE_REPLICAS bundle nodes
	    failures=$(ocf_failures_globally | grep -c -w INFINITY)
	    test $failures -eq $BUNDLE_REPLICAS
	fi
    else
	# bundle failed if all ${BUNDLE_REPLICAS} replicas failed
	failures=$(bundle_failures_globally | grep -c -w INFINITY)
	test $failures -eq $BUNDLE_REPLICAS
    fi
}


# Input validation
#

NAME=$1
if [ -z "${NAME}" ]; then
    echo 2>&1 "Error: argument NAME must not be empty"
    exit 1
fi

BUNDLE_NAME=$2
if [ -z "${BUNDLE_NAME}" ]; then
    echo 2>&1 "Error: argument BUNDLE_NAME must not be empty"
    exit 1
fi

ROLE_LOCAL=$3
if [ "${ROLE_LOCAL}" = "_" ]; then
    ROLE_LOCAL=""
fi

ROLE_ANYWHERE=$4
if [ "${ROLE_ANYWHERE}" = "_" ]; then
    ROLE_ANYWHERE=""
fi

if [ -z "${ROLE_LOCAL}" ]; then
    if [ -z "${ROLE_ANYWHERE}" ]; then
        echo 2>&1 "Error: either ROLE_LOCAL or ROLE_ANYWHERE must be non empty"
        exit 1
    fi
else
    if !(echo "${ROLE_LOCAL}" | grep -q -x -E "(Started|Slave|Master)"); then
        echo 2>&1 "Error: argument ROLE_LOCAL must be either 'Started' 'Slave' or 'Master'"
        exit 1
    fi
fi

if [ -n "${ROLE_ANYWHERE}" ] && !(echo "${ROLE_ANYWHERE}" | grep -q -x -E "(Started|Slave|Master)"); then
    echo 2>&1 "Error: argument ROLE_ANYWHERE must be either 'Started' 'Slave' or 'Master'"
    exit 1
fi

HOST=${5:-$(facter hostname)}
TIMEOUT=${6:-__PCMKTIMEOUT__}


# Configure the search
# ----
# Note: we can't use crm_resource in all searches because we can't
# easily extract the host the OCF resources run on (crm_resource
# returns the pcmk-remote nodes rather than the hosts)
# So instead, we implement various searches with XPath directly.

if [ "${BUNDLE_NAME}" != "${NAME}" ]; then
# ocf resource
local_resource_xpath="//bundle/replica/resource[@resource_agent='ocf::pacemaker:remote']/node[@name='${HOST}']/../../resource[@id='${NAME}']"
any_resource_xpath="//bundle//resource[@id='${NAME}']"
replicas_xpath="//bundle/primitive[@id='${BUNDLE_NAME}']/../*[boolean(@image) and boolean(@replicas)]"
else
# bundle resource
local_resource_xpath="//bundle[@id='${NAME}']/replica/resource/node[@name='${HOST}']/../../resource"
any_resource_xpath="//bundle[@id='${NAME}']//resource"
replicas_xpath="//bundle[@id='${BUNDLE_NAME}']/*[boolean(@image) and boolean(@replicas)]"
fi

bundle_def_xpath="//bundle[@id='${BUNDLE_NAME}']/*[boolean(@image) and boolean(@replicas)]"
BUNDLE_CONTAINER_ENGINE=$(cibadmin -Q | xmllint --xpath "name(${bundle_def_xpath})" -)
BUNDLE_REPLICAS=$(cibadmin -Q | xmllint --xpath "string(${bundle_def_xpath}/@replicas)" -)


# The wait algorithm follows a two-stage approach
#  1. Depending on how the script is called, we first check whether
#     the resource is restarted locally. An A/P resource may be
#     restarted elsewhere in the cluster.
#  2. If needed, check whether the A/P resource has restarted
#     elsewhere. For A/P M/S resources, in case the resource is
#     restarted as Slave locally, ensure a Master is available.

success=1
bailout=1
timeout=$TIMEOUT
role=""

# Stage 1: local check
if [ -n "$ROLE_LOCAL" ]; then
    log "Waiting until ${NAME} has restarted on ${HOST} and is in state ${ROLE_LOCAL}"
    log "Will probe resource state with the following XPath pattern: ${local_resource_xpath}"

    while [ $timeout -gt 0 ] && [ $bailout -ne 0 ] && [ $success -ne 0 ]; do
        resource=$(crm_mon -r --as-xml | xmllint --xpath "${local_resource_xpath}" - 2>/dev/null)
        role=$(echo "${resource}" | sed -ne 's/.*\Wrole="\([^"]*\)".*/\1/p')

	if [ "$(crm_resource --meta -r ${NAME} -g is-managed 2>/dev/null)" = "false" ]; then
            log "${NAME} is unmanaged, will never reach target role. Bailing out"
            bailout=0
            continue
	elif [ "$(crm_resource --meta -r ${NAME} -g target-role 2>/dev/null)" = "Stopped" ]; then
            log "${NAME} is disabled, will never reach target role. Bailing out"
            bailout=0
            continue
        elif echo "${resource}" | grep -q -w "\Wblocked=\"true\""; then
            log "${NAME} is blocked, will never reach target role. Bailing out"
            bailout=0
            continue
	elif did_resource_failed_locally; then
            log "${NAME} is in failed state, will never reach target role. Bailing out"
            bailout=0
            continue
        elif [ "$role" = "$ROLE_LOCAL" ]; then
            success=0
            continue
        elif [ -n "$ROLE_ANYWHERE" ] && [ "$role" = "$ROLE_ANYWHERE" ]; then
            # A/P: we are restarted in the expected state
            success=0
            continue
        else
            log "Waiting for ${NAME} to transition to role ${ROLE_LOCAL} on ${HOST}"
        fi

        if [ $bailout -ne 0 ] && [ $success -ne 0 ]; then
            sleep 4
            timeout=$((timeout-4))
        fi
    done
fi

# Stage 2: global check
if [ $timeout -gt 0 ] && [ -n "$ROLE_ANYWHERE" ] && [ "$role" != "$ROLE_ANYWHERE" ]; then
    log "Wait until ${NAME} is restarted anywhere in the cluster in state ${ROLE_ANYWHERE}"
    log "Will probe resource state with the following XPath pattern: ${any_resource_xpath}"

    success=1
    bailout=1
    while [ $timeout -gt 0 ] && [ $bailout -ne 0 ] && [ $success -ne 0 ]; do
        resources=$(crm_mon -r --as-xml | xmllint --xpath "${any_resource_xpath}" - 2>/dev/null)
	if [ "$(crm_resource --meta -r ${NAME} -g is-managed 2>/dev/null)" = "false" ]; then
            log "${NAME} is unmanaged, will never reach target role. Bailing out"
            bailout=0
            continue
	elif [ "$(crm_resource --meta -r ${NAME} -g target-role 2>/dev/null)" = "Stopped" ]; then
            log "${NAME} is disabled, will never reach target role. Bailing out"
            bailout=0
            continue
        elif ! (echo "${resources}" | grep -q -w "\Wblocked=\"false\""); then
            log "${NAME} blocked, will never reach target role. Bailing out"
            bailout=0
            continue
	elif did_resource_failed_globally; then
            log "${NAME} is in failed state, will never reach target role. Bailing out"
            bailout=0
            continue
        elif echo "${resources}" | grep -q -w "\Wrole=\"${ROLE_ANYWHERE}\""; then
            success=0
            continue
        else
            log "Waiting for ${NAME} to transition to role ${ROLE_ANYWHERE} anywhere in the cluster"
        fi

        if [ $bailout -ne 0 ] && [ $success -ne 0 ]; then
            sleep 4
            timeout=$((timeout-4))
        fi
    done
fi

if [ $timeout -le 0 ]; then
    log "Timeout reached after ${TIMEOUT}s while waiting for ${NAME} to be restarted"
elif [ $bailout -le 0 ]; then
    log "Restart monitoring for ${NAME} cancelled"
fi

if [ $success -eq 0 ]; then
    log "${NAME} successfully restarted"
else
    log "${NAME} was not restarted properly"
fi

# Don't block minor update or stack update if the wait was unsuccessful
exit 0
