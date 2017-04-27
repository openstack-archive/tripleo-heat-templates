#!/bin/bash

set -eu

DEBUG="true" # set false if the verbosity is a problem
SCRIPT_NAME=$(basename $0)
function log_debug {
  if [[ $DEBUG = "true" ]]; then
    echo "`date` $SCRIPT_NAME tripleo-upgrade $(facter hostname) $1"
  fi
}

function is_bootstrap_node {
  if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
    log_debug "Node is bootstrap"
    echo "true"
  fi
}

function check_resource_pacemaker {
  if [ "$#" -ne 3 ]; then
    echo_error "ERROR: check_resource function expects 3 parameters, $# given"
    exit 1
  fi

  local service=$1
  local state=$2
  local timeout=$3

  if [[ -z $(is_bootstrap_node) ]] ; then
    log_debug "Node isn't bootstrap, skipping check for $service to be $state here "
    return
  else
    log_debug "Node is bootstrap checking $service to be $state here"
  fi

  if [ "$state" = "stopped" ]; then
    match_for_incomplete='Started'
  else # started
    match_for_incomplete='Stopped'
  fi

  nodes_local=$(pcs status  | grep ^Online | sed 's/.*\[ \(.*\) \]/\1/g' | sed 's/ /\|/g')
  if timeout -k 10 $timeout crm_resource --wait; then
    node_states=$(pcs status --full | grep "$service" | grep -v Clone | { egrep "$nodes_local" || true; } )
    if echo "$node_states" | grep -q "$match_for_incomplete"; then
      echo_error "ERROR: cluster finished transition but $service was not in $state state, exiting."
      exit 1
    else
      echo "$service has $state"
    fi
  else
    echo_error "ERROR: cluster remained unstable for more than $timeout seconds, exiting."
    exit 1
  fi

}

function pcmk_running {
  if [[ $(systemctl is-active pacemaker) = "active" ]] ; then
    echo "true"
  fi
}

function is_systemd_unknown {
  local service=$1
  if [[ $(systemctl is-active "$service") = "unknown" ]]; then
    log_debug "$service found to be unkown to systemd"
    echo "true"
  fi
}

function grep_is_cluster_controlled {
  local service=$1
  if [[ -n $(systemctl status $service -l | grep Drop-In -A 5 | grep pacemaker) ||
      -n $(systemctl status $service -l | grep "Cluster Controlled $service") ]] ; then
    log_debug "$service is pcmk managed from systemctl grep"
    echo "true"
  fi
}


function is_systemd_managed {
  local service=$1
  #if we have pcmk check to see if it is managed there
  if [[ -n $(pcmk_running) ]]; then
    if [[ -z $(pcs status --full | grep $service)  && -z $(is_systemd_unknown $service) ]] ; then
      log_debug "$service found to be systemd managed from pcs status"
      echo "true"
    fi
  else
    # if it is "unknown" to systemd, then it is pacemaker managed
    if [[  -n $(is_systemd_unknown $service) ]] ; then
      return
    elif [[ -z $(grep_is_cluster_controlled $service) ]] ; then
      echo "true"
    fi
  fi
}

function is_pacemaker_managed {
  local service=$1
  #if we have pcmk check to see if it is managed there
  if [[ -n $(pcmk_running) ]]; then
    if [[ -n $(pcs status --full | grep $service) ]]; then
      log_debug "$service found to be pcmk managed from pcs status"
      echo "true"
    fi
  else
    # if it is unknown to systemd, then it is pcmk managed
    if [[ -n $(is_systemd_unknown $service) ]]; then
      echo "true"
    elif [[ -n $(grep_is_cluster_controlled $service) ]] ; then
      echo "true"
    fi
  fi
}

function is_managed {
  local service=$1
  if [[ -n $(is_pacemaker_managed $service) || -n $(is_systemd_managed $service) ]]; then
    echo "true"
  fi
}

function check_resource_systemd {

  if [ "$#" -ne 3 ]; then
    echo_error "ERROR: check_resource function expects 3 parameters, $# given"
    exit 1
  fi

  local service=$1
  local state=$2
  local timeout=$3
  local check_interval=3

  if [ "$state" = "stopped" ]; then
    match_for_incomplete='active'
  else # started
    match_for_incomplete='inactive'
  fi

  log_debug "Going to check_resource_systemd for $service to be $state"

  #sanity check is systemd managed:
  if [[ -z $(is_systemd_managed $service) ]]; then
    echo "ERROR - $service not found to be systemd managed."
    exit 1
  fi

  tstart=$(date +%s)
  tend=$(( $tstart + $timeout ))
  while (( $(date +%s) < $tend )); do
    if [[ "$(systemctl is-active $service)" = $match_for_incomplete ]]; then
      echo "$service not yet $state, sleeping $check_interval seconds."
      sleep $check_interval
    else
      echo "$service is $state"
      return
    fi
  done

  echo "Timed out waiting for $service to go to $state after $timeout seconds"
  exit 1
}


function check_resource {
  local service=$1
  local pcmk_managed=$(is_pacemaker_managed $service)
  local systemd_managed=$(is_systemd_managed $service)

  if [[ -n $pcmk_managed && -n $systemd_managed ]] ; then
    log_debug "ERROR $service managed by both systemd and pcmk - SKIPPING"
    return
  fi

  if [[ -n $pcmk_managed ]]; then
    check_resource_pacemaker $@
    return
  elif [[ -n $systemd_managed ]]; then
    check_resource_systemd $@
    return
  fi
  log_debug "ERROR cannot check_resource for $service, not managed here?"
}

function manage_systemd_service {
  local action=$1
  local service=$2
  log_debug "Going to systemctl $action $service"
  systemctl $action $service
}

function manage_pacemaker_service {
  local action=$1
  local service=$2
  # not if pacemaker isn't running!
  if [[ -z $(pcmk_running) ]]; then
    echo "$(facter hostname) pacemaker not active, skipping $action $service here"
  elif [[ -n $(is_bootstrap_node) ]]; then
    log_debug "Going to pcs resource $action $service"
    pcs resource $action $service
  fi
}

function stop_or_disable_service {
  local service=$1
  local pcmk_managed=$(is_pacemaker_managed $service)
  local systemd_managed=$(is_systemd_managed $service)

  if [[ -n $pcmk_managed && -n $systemd_managed ]] ; then
    log_debug "Skipping stop_or_disable $service due to management conflict"
    return
  fi

  log_debug "Stopping or disabling $service"
  if [[ -n $pcmk_managed ]]; then
    manage_pacemaker_service disable $service
    return
  elif [[ -n $systemd_managed ]]; then
    manage_systemd_service stop $service
    return
  fi
  log_debug "ERROR: $service not managed here?"
}

function start_or_enable_service {
  local service=$1
  local pcmk_managed=$(is_pacemaker_managed $service)
  local systemd_managed=$(is_systemd_managed $service)

  if [[ -n $pcmk_managed && -n $systemd_managed ]] ; then
    log_debug "Skipping start_or_enable $service due to management conflict"
    return
  fi

  log_debug "Starting or enabling $service"
  if [[ -n $pcmk_managed ]]; then
    manage_pacemaker_service enable $service
    return
  elif [[ -n $systemd_managed ]]; then
    manage_systemd_service start $service
    return
  fi
  log_debug "ERROR $service not managed here?"
}

function restart_service {
  local service=$1
  local pcmk_managed=$(is_pacemaker_managed $service)
  local systemd_managed=$(is_systemd_managed $service)

  if [[ -n $pcmk_managed && -n $systemd_managed ]] ; then
    log_debug "ERROR $service managed by both systemd and pcmk - SKIPPING"
    return
  fi

  log_debug "Restarting $service"
  if [[ -n $pcmk_managed ]]; then
    manage_pacemaker_service restart $service
    return
  elif [[ -n $systemd_managed ]]; then
    manage_systemd_service restart $service
    return
  fi
  log_debug "ERROR $service not managed here?"
}

function echo_error {
    echo "$@" | tee /dev/fd2
}

# swift is a special case because it is/was never handled by pacemaker
# when stand-alone swift is used, only swift-proxy is running on controllers
function systemctl_swift {
    services=( openstack-swift-account-auditor openstack-swift-account-reaper openstack-swift-account-replicator openstack-swift-account \
               openstack-swift-container-auditor openstack-swift-container-replicator openstack-swift-container-updater openstack-swift-container \
               openstack-swift-object-auditor openstack-swift-object-replicator openstack-swift-object-updater openstack-swift-object openstack-swift-proxy )
    local action=$1
    case $action in
        stop)
            services=$(systemctl | grep openstack-swift- | grep running | awk '{print $1}')
            ;;
        start)
            enable_swift_storage=$(hiera -c /etc/puppet/hiera.yaml tripleo::profile::base::swift::storage::enable_swift_storage)
            if [[ $enable_swift_storage != "true" ]]; then
                services=( openstack-swift-proxy )
            fi
            ;;
        *)  echo "Unknown action $action passed to systemctl_swift"
            exit 1
            ;; # shouldn't ever happen...
    esac
    for service in ${services[@]}; do
        manage_systemd_service $action $service
    done
}

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1635205
# Update condition and add --notriggerun for +bug/1669714
function special_case_ovs_upgrade_if_needed {
    if rpm -qa | grep "^openvswitch-2.5.0-14" || rpm -q --scripts openvswitch | awk '/postuninstall/,/*/' | grep "systemctl.*try-restart" ; then
        echo "Manual upgrade of openvswitch - ovs-2.5.0-14 or restart in postun detected"
        rm -rf OVS_UPGRADE
        mkdir OVS_UPGRADE && pushd OVS_UPGRADE
        echo "Attempting to downloading latest openvswitch with yumdownloader"
        yumdownloader --resolve openvswitch
        for pkg in $(ls -1 *.rpm);  do
            if rpm -U --test $pkg 2>&1 | grep "already installed" ; then
                echo "Looks like newer version of $pkg is already installed, skipping"
            else
                echo "Updating $pkg with --nopostun --notriggerun"
                rpm -U --replacepkgs --nopostun --notriggerun $pkg
            fi
        done
        popd
    else
        echo "Skipping manual upgrade of openvswitch - no restart in postun detected"
    fi

}

# This code is meant to fix https://bugs.launchpad.net/tripleo/+bug/1686357 on
# existing setups via a minor update workflow and be idempotent. We need to
# run this before the yum update because we fix this up even when there are no
# packages to update on the system (in which case the script exits).
# This code must be called with set +eu (due to the ocf scripts being sourced)
function fixup_wrong_ipv6_vip {
    # This XPath query identifies of all the VIPs in pacemaker with netmask /64. Those are IPv6 only resources that have the wrong netmask
    # This gives the address of the resource in the CIB, one address per line. For example:
    # /cib/configuration/resources/primitive[@id='ip-2001.db8.ca2.4..10']/instance_attributes[@id='ip-2001.db8.ca2.4..10-instance_attributes']\
    # /nvpair[@id='ip-2001.db8.ca2.4..10-instance_attributes-cidr_netmask']
    vip_xpath_query="//resources/primitive[@type='IPaddr2']/instance_attributes/nvpair[@name='cidr_netmask' and @value='64']"
    vip_xpath_xml_addresses=$(cibadmin --query --xpath "$vip_xpath_query" -e 2>/dev/null)
    # The following extracts the @id value of the resource
    vip_resources_to_fix=$(echo -e "$vip_xpath_xml_addresses" | sed -n "s/.*primitive\[@id='\([^']*\)'.*/\1/p")
    # Runnning this in a subshell so that sourcing files cannot possibly affect the running script
    (
        OCF_PATH="/usr/lib/ocf/lib/heartbeat"
        if [ -n "$vip_resources_to_fix" -a -f $OCF_PATH/ocf-shellfuncs -a -f $OCF_PATH/findif.sh ]; then
            source $OCF_PATH/ocf-shellfuncs
            source $OCF_PATH/findif.sh
            for resource in $vip_resources_to_fix; do
                echo "Updating IPv6 VIP $resource with a /128 and a correct addrlabel"
                # The following will give us something like:
                # <nvpair id="ip-2001.db8.ca2.4..10-instance_attributes-ip" name="ip" value="2001:db8:ca2:4::10"/>
                ip_cib_nvpair=$(cibadmin --query --xpath "//resources/primitive[@type='IPaddr2' and @id='$resource']/instance_attributes/nvpair[@name='ip']")
                # Let's filter out the value of the nvpair to get the ip address
                ip_address=$(echo $ip_cib_nvpair | xmllint --xpath 'string(//nvpair/@value)' -)
                OCF_RESKEY_cidr_netmask="64"
                OCF_RESKEY_ip="$ip_address"
                # Unfortunately due to https://bugzilla.redhat.com/show_bug.cgi?id=1445628
                # we need to find out the appropiate nic given the ip address.
                nic=$(findif $ip_address | awk '{ print $1 }')
                ret=$?
                if [ -z "$nic" -o $ret -ne 0 ]; then
                    echo "NIC autodetection failed for VIP $ip_address, not updating VIPs"
                    # Only exits the subshell
                    exit 1
                fi
                ocf_run -info pcs resource update --wait "$resource" ip="$ip_address" cidr_netmask=128 nic="$nic" lvs_ipv6_addrlabel=true lvs_ipv6_addrlabel_value=99
                ret=$?
                if [ $ret -ne 0 ]; then
                    echo "pcs resource update for VIP $resource failed, not updating VIPs"
                    # Only exits the subshell
                    exit 1
                fi
            done
        fi
    )
}
