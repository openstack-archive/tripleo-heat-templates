#!/bin/bash

# For each unique remote IP (specified via Heat) we check to
# see if one of the locally configured networks matches and if so we
# attempt a ping test on that networks remote IP.
function ping_controller_ips() {
  local REMOTE_IPS=$1
  for REMOTE_IP in $(echo $REMOTE_IPS | sed -e "s| |\n|g" | sort -u); do
    if [[ $REMOTE_IP =~ ":" ]]; then
      networks=$(ip -6 r | grep -v default | cut -d " " -f 1 | grep -v "unreachable")
      ping=ping6
    else
      networks=$(ip r | grep -v default | cut -d " " -f 1)
      ping=ping
    fi
    for LOCAL_NETWORK in $networks; do
      in_network=$(python -c "import ipaddr; net=ipaddr.IPNetwork('$LOCAL_NETWORK'); addr=ipaddr.IPAddress('$REMOTE_IP'); print(addr in net)")
      if [[ $in_network == "True" ]]; then
        echo -n "Trying to ping $REMOTE_IP for local network $LOCAL_NETWORK..."
        if ! $ping -W 300 -c 1 $REMOTE_IP &> /dev/null; then
          echo "FAILURE"
          echo "$REMOTE_IP is not pingable. Local Network: $LOCAL_NETWORK" >&2
          exit 1
        fi
        echo "SUCCESS"
      fi
    done
  done
}

ping_controller_ips "$ping_test_ips"
