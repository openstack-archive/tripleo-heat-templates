#!/bin/bash

set -u

# ./pacemaker_restart_bundle.sh mysql galera galera-bundle Master _
# ./pacemaker_restart_bundle.sh redis redis redis-bundle Slave Master
# ./pacemaker_restart_bundle.sh ovn_dbs ovndb_servers ovn-dbs-bundle Slave Master
RESTART_SCRIPTS_DIR=$(dirname $0)
TRIPLEO_SERVICE=$1
RESOURCE_NAME=$2
BUNDLE_NAME=$3
WAIT_TARGET_LOCAL=$4
WAIT_TARGET_ANYWHERE=${5:-_}
TRIPLEO_MINOR_UPDATE="${TRIPLEO_MINOR_UPDATE:-false}"


bundle_can_be_restarted() {
    local bundle=$1
    # As long as the resource bundle is managed by pacemaker and is
    # not meant to stay stopped, no matter the state of any inner
    # pcmk_remote or ocf resource, we should restart it to give it a
    # chance to read the new config.
    [ "$(crm_resource --meta -r $1 -g is-managed 2>/dev/null)" != "false" ] && \
    [ "$(crm_resource --meta -r $1 -g target-role 2>/dev/null)" != "Stopped" ]
}


if [ x"${TRIPLEO_MINOR_UPDATE,,}" != x"true" ]; then
    if hiera -c /etc/puppet/hiera.yaml stack_action | grep -q -x CREATE; then
        # Do not restart during initial deployment, as the resource
        # has just been created.
        exit 0
    else
        # During a stack update, this script is called in parallel on
        # every node the resource runs on, after the service's configs
        # have been updated on all nodes. So we need to run pcs only
        # once (e.g. on the service's boostrap node).
        if bundle_can_be_restarted ${BUNDLE_NAME}; then
            echo "$(date -u): Restarting ${BUNDLE_NAME} globally"
            /usr/bin/bootstrap_host_exec $TRIPLEO_SERVICE /sbin/pcs resource restart --wait=__PCMKTIMEOUT__ $BUNDLE_NAME
        else
            echo "$(date -u): No global restart needed for ${BUNDLE_NAME}."
        fi
    fi
else
    # During a minor update workflow however, a host gets fully
    # updated before updating the next one. So unlike stack
    # update, at the time this script is called, the service's
    # configs aren't updated on all nodes yet. So only restart the
    # resource locally, where it's guaranteed that the config is
    # up to date.
    HOST=$(facter hostname)

    if bundle_can_be_restarted ${BUNDLE_NAME}; then
	# if the resource is running locally, restart it
	if crm_resource -r $BUNDLE_NAME --locate 2>&1 | grep -w -q "${HOST}"; then
            echo "$(date -u): Restarting ${BUNDLE_NAME} locally on '${HOST}'"
            /sbin/pcs resource restart $BUNDLE_NAME "${HOST}"

	else
	    # At this point, if no resource is running locally, it's
	    # either because a) it has failed previously, or b) because
	    # it's an A/P resource running elsewhere.
	    # By cleaning up resource, we ensure that a) it will try to
	    # restart, or b) it won't do anything if the resource is
	    # already running elsewhere.
            echo "$(date -u): ${BUNDLE_NAME} is currently not running on '${HOST}'," \
                 "cleaning up its state to restart it if necessary"
            /sbin/pcs resource cleanup $BUNDLE_NAME --node "${HOST}"
	fi

	# Wait until the resource is in the expected target state
	$RESTART_SCRIPTS_DIR/pacemaker_wait_bundle.sh \
            $RESOURCE_NAME $BUNDLE_NAME \
            "$WAIT_TARGET_LOCAL" "$WAIT_TARGET_ANYWHERE" \
	    "${HOST}" __PCMKTIMEOUT__
    else
        echo "$(date -u): No restart needed for ${BUNDLE_NAME}."
    fi
fi
