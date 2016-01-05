#!/bin/bash

set -eux

pacemaker_status=$(systemctl is-active pacemaker)
check_interval=3

function check_resource {

  service=$1
  state=$2
  timeout=$3
  tstart=$(date +%s)
  tend=$(( $tstart + $timeout ))

  if [ "$state" = "stopped" ]; then
      match_for_incomplete='Started'
  else # started
      match_for_incomplete='Stopped'
  fi

  while (( $(date +%s) < $tend )); do
      node_states=$(pcs status --full | grep "$service" | grep -v Clone)
      if echo "$node_states" | grep -q "$match_for_incomplete"; then
          echo "$service not yet $state, sleeping $check_interval seconds."
          sleep $check_interval
      else
        echo "$service has $state"
        return
      fi
  done

  echo "$service never $state after $timeout seconds" | tee /dev/fd/2
  exit 1

}

# Run if pacemaker is running, we're the bootstrap node,
# and we're updating the deployment (not creating).
if [ "$pacemaker_status" = "active" -a \
     "$(hiera bootstrap_nodeid)" = "$(facter hostname)" -a \
     "$(hiera update_identifier)" != "nil" ]; then

    #ensure neutron constraints like
    #https://review.openstack.org/#/c/245093/
    if  pcs constraint order show  | grep "start neutron-server-clone then start neutron-ovs-cleanup-clone"; then
        pcs constraint remove order-neutron-server-clone-neutron-ovs-cleanup-clone-mandatory
    fi

    pcs resource disable httpd
    check_resource httpd stopped 300
    pcs resource disable openstack-keystone
    check_resource openstack-keystone stopped 1200

    if pcs status | grep haproxy-clone; then
        pcs resource restart haproxy-clone
    fi
    pcs resource restart redis-master
    pcs resource restart mongod-clone
    pcs resource restart rabbitmq-clone
    pcs resource restart memcached-clone
    pcs resource restart galera-master

    pcs resource enable openstack-keystone
    check_resource openstack-keystone started 300
    pcs resource enable httpd
    check_resource httpd started 800

fi
