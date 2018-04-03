#!/bin/bash

set -eu

DEBUG="true" # set false if the verbosity is a problem
SCRIPT_NAME=$(basename $0)

# This block get default for ovs fail mode handling during upgrade.
function get_all_bridges {
    local bridges_def=""
    local bridges=""
    if which ovs-vsctl &>/dev/null; then
      if [ -e /etc/neutron/plugins/ml2/openvswitch_agent.ini ]; then
        local raw_bridge_def=$(crudini --get /etc/neutron/plugins/ml2/openvswitch_agent.ini ovs bridge_mappings)
        local bridges=""
        while IFS=: read physnet bridge; do bridges_def="${bridges_def} ${bridge}" ; done \
          < <(echo "${raw_bridge_def}" | sed 's/,/\n/g')
        local existing_bridges="$(ovs-vsctl -f table -d bare --column=name --no-headings find Bridge)"
        for br in ${bridges_def}; do
            if echo "${existing_bridges}" | grep -q $br; then
              bridges="${bridges} ${br}"
            fi
        done
      fi
    fi
    echo "${bridges}"
}

function log_debug {
  if [[ $DEBUG = "true" ]]; then
    echo "`date` $SCRIPT_NAME tripleo-upgrade $(facter hostname) $1"
  fi
}

function is_bootstrap_node {
  if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid | tr '[:upper:]' '[:lower:]')" = "$(facter hostname | tr '[:upper:]' '[:lower:]')" ]; then
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

# Special case for OVS 2.9 where we need to change the OVS config file
# to run with the right user
function change_ovs_2_9_user {
    local ovs_config_file="/etc/sysconfig/openvswitch"

    if ! grep -q '^OVS_USER_ID="*openvswitch:hugetlbfs"*' $ovs_config_file; then
        if grep -q "^\#*OVS_USER_ID=" $ovs_config_file; then
            sed -i 's/^\#*OVS_USER_ID=.*/OVS_USER_ID="openvswitch:hugetlbfs"/' $ovs_config_file
        else
            sed -i '$ a OVS_USER_ID="openvswitch:hugetlbfs"' $ovs_config_file
        fi
    fi
}

# Special case for OVS 2.9 where we need to create a one-time service file,
# that will change any remaining permissions after reboot if needed
function change_ovs_2_9_perms {
    local ovs_owner=$(find /etc/openvswitch /var/log/openvswitch ! -user openvswitch ! -group hugetlbfs 2> /dev/null)
    if [ ! -z "${ovs_owner}" ]; then
            cat >/etc/systemd/system/multi-user.target.wants/fix-ovs-permissions.service <<EOL
[Unit]
Description=One time service to fix permissions in OpenvSwitch
Before=openvswitch.service

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/bash -c "/usr/bin/chown -R openvswitch:hugetlbfs /etc/openvswitch /var/log/openvswitch || true"
ExecStartPost=/usr/bin/rm /etc/systemd/system/multi-user.target.wants/fix-ovs-permissions.service
TimeoutStartSec=0
RemainAfterExit=no

[Install]
WantedBy=default.target
EOL
        chmod a+x /etc/systemd/system/multi-user.target.wants/fix-ovs-permissions.service
    fi
}

# Special-case OVS for https://bugs.launchpad.net/tripleo/+bug/1635205
# Update condition and add --notriggerun for +bug/1669714
function special_case_ovs_upgrade_if_needed {
    # Always ensure yum has full cache
    yum makecache || echo "Yum makecache failed. This can cause failure later on."
    # Ovs uses openvswitch:hugetlbfs as user and group settings
    # when updating to 2.8 onwards, but openvswitch user is not
    # created during package update. This adds workaround to
    # make sure openvswitch user exist before running package
    # update. Details can be found at:
    # https://bugzilla.redhat.com/show_bug.cgi?id=1559374
    # 42477 is the kolla hugetlbfs gid value.
    getent group hugetlbfs >/dev/null || \
        groupadd hugetlbfs -g 42477 && groupmod -g 42477 hugetlbfs
    getent passwd openvswitch >/dev/null || \
        useradd -r -d / -s /sbin/nologin -c "Open vSwitch Daemons" openvswitch
    usermod -a -G hugetlbfs openvswitch

    # first check if ovs needs upgrade
    OVS_NEEDS_UPGRADE=$(yum check-upgrade openvswitch | awk '/openvswitch/{print}')
    if [ -z "${OVS_NEEDS_UPGRADE}" ]; then
        echo "Looks like newer version of openvswitch is already installed, skipping"
    else
        if rpm -qa | grep "^openvswitch-2.5.0-14" || rpm -q --scripts openvswitch | awk '/postuninstall/,/*/' | grep "systemctl.*try-restart" ; then
            echo "Manual upgrade of openvswitch - ovs-2.5.0-14 or restart in postun detected"
            rm -rf OVS_UPGRADE
            mkdir OVS_UPGRADE && pushd OVS_UPGRADE
            echo "Attempting to downloading latest openvswitch with yumdownloader"
            yumdownloader --resolve openvswitch
            for pkg in $(ls -1 *.rpm);  do
                echo "Updating $pkg with --nopostun --notriggerun"
                rpm -U --replacepkgs --nopostun --notriggerun $pkg
                break
            done
            popd

        else
            echo "Skipping manual upgrade of openvswitch - no restart in postun detected. Performing automated upgrade"
            yum update -y openvswitch
        fi

        change_ovs_2_9_user
        change_ovs_2_9_perms
    fi
}

function special_case_iptables_services_upgrade_if_needed {
    # Always ensure yum has full cache
    yum makecache || echo "Yum makecache failed. This can cause failure later on."
    # Return 0 when no upgrade is needed
    if yum check-upgrade iptables-services; then
        echo "Either iptables-services is not installed or a newer version is already there, skipping workaround."
    fi
    if rpm -q --scripts iptables-services | awk '/postuninstall/,/*/' | grep "systemctl.*try-restart" ; then
        echo "Manual upgrade of iptables-services - restart in postun detected"
        rm -rf ~/IPTABLES_UPGRADE
        mkdir -p ~/IPTABLES_UPGRADE && pushd ~/IPTABLES_UPGRADE
        echo "Attempting to download latest iptables-services with yumdownloader"
        yumdownloader iptables-services # no deps on purpose.
        pkg="$(ls -1 iptables-services-*.x86_64.rpm)"
        if [ -z "${pkg}" ]; then
            echo "Cannot find a valid package for iptables-services, aborting"
            exit 1
        fi
        echo "Updating iptables-services to $pkg with --nopostun --notriggerun --nodeps"
        rpm -U --replacepkgs --nopostun --notriggerun --nodeps ./${pkg}
        systemctl daemon-reload
        popd
    else
        echo "Skipping manual upgrade of iptables-services  - no restart in postun detected"
    fi
}

# update os-net-config before ovs see https://bugs.launchpad.net/tripleo/+bug/1695893
function update_os_net_config() {
  set +e
  local need_update="$(yum check-upgrade | grep os-net-config)"
  if [ -n "${need_update}" ]; then
      yum -q -y update os-net-config
      local return_code=$?
      echo "`date` yum update os-net-config return code: $return_code"
      if [ -s "/etc/os-net-config/config.json" ]; then
          # We're just make sure that os-net-config won't ifdown/ifup
          # network interfaces.  The current set of changes (Tue Oct 3
          # 17:38:37 CEST 2017) doesn't require the os-net-config change
          # to be taken live.  They will be at next reboot.
          os-net-config --no-activate -c /etc/os-net-config/config.json -v \
                        --detailed-exit-codes
          local os_net_retval=$?
          if [[ $os_net_retval == 2 ]]; then
              echo "`date` os-net-config: interface configuration files updated successfully"
          elif [[ $os_net_retval != 0 ]]; then
              echo "`date` ERROR: os-net-config configuration failed"
              exit $os_net_retval
          fi
      else
          echo "`date` /etc/os-net-config/config.json doesn't exist or is empty.  No need to run os-net-config."
      fi
  fi
  set -e
}

function update_network() {
    update_os_net_config
    # special case https://bugs.launchpad.net/tripleo/+bug/1635205 +bug/1669714
    special_case_ovs_upgrade_if_needed
    special_case_iptables_services_upgrade_if_needed
}

# https://bugs.launchpad.net/tripleo/+bug/1704131 guard against yum update
# waiting for an existing process until the heat stack time out
function check_for_yum_lock {
    if [[ -f /var/run/yum.pid ]] ; then
        ERR="ERROR existing yum.pid detected - can't continue! Please ensure
there is no other package update process for the duration of the minor update
worfklow. Exiting."
        echo $ERR
        exit 1
   fi
}
