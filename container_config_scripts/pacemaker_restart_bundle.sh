#!/bin/bash

set -u

# ./pacemaker_restart_bundle.sh galera-bundle galera
RESOURCE=$1
TRIPLEO_SERVICE=$2

# try to restart only if resource has been created already
if /usr/sbin/pcs resource show $RESOURCE; then
    if [ x"${TRIPLEO_MINOR_UPDATE,,}" != x"true" ]; then
        # During a stack update, this script is called in parallel on
        # every node the resource runs on, after the service's configs
        # have been updated on all nodes. So we need to run pcs only
        # once (e.g. on the service's boostrap node).
        echo "$(date -u): Restarting ${RESOURCE} globally"
        /usr/bin/bootstrap_host_exec $TRIPLEO_SERVICE /sbin/pcs resource restart --wait=__PCMKTIMEOUT__ $RESOURCE
    else
        # During a minor update workflow however, a host gets fully
        # updated before updating the next one. So unlike stack
        # update, at the time this script is called, the service's
        # configs aren't updated on all nodes yet. So only restart the
        # resource locally, where it's guaranteed that the config is
        # up to date.
        HOST=$(facter hostname)
        # XPath rationale: as long as there is a bundle running
        # locally and it is managed by pacemaker, no matter the state
        # of any inner pcmk_remote or ocf resource, we should restart
        # it to give it a chance to read the new config.
        # XPath rationale 2: if the resource is being stopped, the
        # attribute "target_role" will be present in the output of
        # crm_mon. Do not restart the resource if that is the case.
        if crm_mon -r --as-xml | xmllint --format --xpath "//bundle[@id='${RESOURCE}']/replica/resource[@managed='true' and (not(boolean(@target_role)) or (boolean(@target_role) and @target_role!='Stopped'))]/node[@name='${HOST}']/../.." - &>/dev/null; then
            echo "$(date -u): Restarting ${RESOURCE} locally on '${HOST}'"
            /sbin/pcs resource restart --wait=__PCMKTIMEOUT__ $RESOURCE "${HOST}"
        else
            echo "$(date -u): Resource ${RESOURCE} currently not running on '${HOST}', no restart needed"
        fi
    fi
fi
