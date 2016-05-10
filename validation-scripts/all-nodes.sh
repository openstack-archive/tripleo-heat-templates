#!/bin/bash
set -e

function ping_retry() {
  local IP_ADDR=$1
  local TIMES=${2:-'10'}
  local COUNT=0
  local PING_CMD=ping
  if [[ $IP_ADDR =~ ":" ]]; then
    PING_CMD=ping6
  fi
  until [ $COUNT -ge $TIMES ]; do
    if $PING_CMD -w 300 -c 1 $IP_ADDR &> /dev/null; then
      echo "Ping to $IP_ADDR succeeded."
      return 0
    fi
    echo "Ping to $IP_ADDR failed. Retrying..."
    COUNT=$(($COUNT + 1))
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
      networks=$(ip r | grep -v default | cut -d " " -f 1)
    fi
    for LOCAL_NETWORK in $networks; do
      in_network=$(python -c "import ipaddr; net=ipaddr.IPNetwork('$LOCAL_NETWORK'); addr=ipaddr.IPAddress('$REMOTE_IP'); print(addr in net)")
      if [[ $in_network == "True" ]]; then
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
  DEFAULT_GW=$(ip r | grep ^default | cut -d " " -f 3)
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

ping_controller_ips "$ping_test_ips"
ping_default_gateways
