#!/bin/bash

function run_puppet {
    set -eux
    local manifest="$1"
    local role="$2"
    local step="$3"
    local rc=0

    export FACTER_deploy_config_name="${role}Deployment_Step${step}"
    if [ -e "/etc/puppet/hieradata/heat_config_${FACTER_deploy_config_name}.json" ]; then
        set +e
        puppet apply --detailed-exitcodes \
               --modulepath \
               --summarize \
               /etc/puppet/modules:/opt/stack/puppet-modules:/usr/share/openstack-puppet/modules \
               "${manifest}"
        rc=$?
        echo "puppet apply exited with exit code $rc"
    else
        echo "Step${step} doesn't exist for ${role}"
    fi
    set -e

    if [ $rc -eq 2 -o $rc -eq 0 ]; then
        set +xu
        return 0
    fi
    set +xu
    return $rc
}
