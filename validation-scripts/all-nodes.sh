#!/bin/bash

# For each unique remote IP (specified via Heat) we check to
# see if one of the locally configured networks matches and if so we
# attempt a ping test on that networks remote IP.
function ping_controller_ips() {
  local REMOTE_IPS=$1

  for REMOTE_IP in $(echo $REMOTE_IPS | sed -e "s| |\n|g" | sort -u); do

    for LOCAL_NETWORK in $(ip r | grep -v default | cut -d " " -f 1); do
       local LOCAL_CIDR=$(echo $LOCAL_NETWORK | cut -d "/" -f 2)
       local LOCAL_NETMASK=$(ipcalc -m $LOCAL_NETWORK | grep NETMASK | cut -d "=" -f 2)
       local REMOTE_NETWORK=$(ipcalc -np $REMOTE_IP $LOCAL_NETMASK | grep NETWORK | cut -d "=" -f 2)

       if [ $REMOTE_NETWORK/$LOCAL_CIDR == $LOCAL_NETWORK ]; then
         echo -n "Trying to ping $REMOTE_IP for local network $LOCAL_NETWORK..."
         if ! ping -c 1 $REMOTE_IP &> /dev/null; then
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
