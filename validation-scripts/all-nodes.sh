#!/bin/bash
set -e

# needed to handle where python lives
function get_python() {
  command -v python3 || command -v python2 || command -v python || exit 1
}

function ping_retry() {
  local IP_ADDR=$1
  local TIMES=${2:-'10'}
  local COUNT=0
  local PING_CMD=ping
  if [[ $IP_ADDR =~ ":" ]]; then
    PING_CMD=ping6
  fi
  until [ $COUNT -ge $TIMES ]; do
    if $PING_CMD -w 10 -c 1 $IP_ADDR &> /dev/null; then
      echo "Ping to $IP_ADDR succeeded."
      return 0
    fi
    echo "Ping to $IP_ADDR failed. Retrying..."
    COUNT=$(($COUNT + 1))
    sleep 60
  done
  return 1
}

# For each unique remote IP (specified via Heat) we check to
# see if one of the locally configured networks matches and if so we
# attempt a ping test the remote network IP.
function ping_controller_ips() {
  local REMOTE_IPS=$1
  for REMOTE_IP in $(echo $REMOTE_IPS | sed -e "s| |\n|g" | sort -u); do
    if [[ $REMOTE_IP =~ ":" ]]; then
      networks=$(ip -6 r | grep -v default | cut -d " " -f 1 | grep -v "unreachable")
    else
      networks=$(ip r | grep -E '^([0-9]{1,3}\.?){4}' | cut -d " " -f 1)
    fi
    for LOCAL_NETWORK in $networks; do
      in_network=$($(get_python) -c "import ipaddress; net=ipaddress.ip_network(u'$LOCAL_NETWORK'); addr=ipaddress.ip_address(u'$REMOTE_IP'); print(addr in net)")
      if [[ "${in_network,,}" == "true" ]]; then
        echo "Trying to ping $REMOTE_IP for local network ${LOCAL_NETWORK}."
        set +e
        if ! ping_retry $REMOTE_IP; then
          echo "FAILURE"
          echo "$REMOTE_IP is not pingable. Local Network: $LOCAL_NETWORK" >&2
          exit 1
        fi
        set -e
        echo "SUCCESS"
      fi
    done
  done
}

# Ping all default gateways. There should only be one
# if using upstream t-h-t network templates but we test
# all of them should some manual network config have
# multiple gateways.
function ping_default_gateways() {
  DEFAULT_GW=$(ip ro | awk '/^default/ {print $3}')
  set +e
  for GW in $DEFAULT_GW; do
    echo -n "Trying to ping default gateway ${GW}..."
    if ! ping_retry $GW; then
      echo "FAILURE"
      echo "$GW is not pingable."
      exit 1
    fi
  done
  set -e
  echo "SUCCESS"
}

# Verify the FQDN from the nova/ironic deployment matches
# FQDN in the heat templates.
function fqdn_check() {
  HOSTNAME=$(hostname)
  SHORT_NAME=$(hostname -s)
  FQDN_FROM_HOSTS=$(awk '$3 == "'${SHORT_NAME}'"{print $2}' /etc/hosts)
  echo -n "Checking hostname vs /etc/hosts entry..."
  if [[ $HOSTNAME != $FQDN_FROM_HOSTS ]]; then
    echo "FAILURE"
    echo -e "System hostname: ${HOSTNAME}\nEntry from /etc/hosts: ${FQDN_FROM_HOSTS}\n"
    exit 1
  fi
  echo "SUCCESS"
}

if [[ "${validate_gateways_icmp,,}" == "true" ]];then
  ping_default_gateways
fi
if [[ "${validate_controllers_icmp,,}" == "true" ]];then
  ping_controller_ips $(echo "$ping_test_ips" | jq -r ".$tripleo_role_name")
fi
if [[ "${validate_fqdn,,}" == "true" ]];then
  fqdn_check
fi
