#!/bin/bash
#
# This delivers the ceph-storage upgrade script to be invoked as part of the tripleo
# major upgrade workflow.
#
set -eu
set -o pipefail

UPGRADE_SCRIPT=/root/tripleo_upgrade_node.sh

declare -f update_os_net_config > $UPGRADE_SCRIPT
declare -f special_case_iptables_services_upgrade_if_needed >> $UPGRADE_SCRIPT
declare -f special_case_ovs_upgrade_if_needed >> $UPGRADE_SCRIPT
declare -f update_network >> $UPGRADE_SCRIPT
# use >> here so we don't lose the declaration we added above
cat >> $UPGRADE_SCRIPT << 'ENDOFCAT'
#!/bin/bash
### DO NOT MODIFY THIS FILE
### This file is automatically delivered to the ceph-storage nodes as part of the
### tripleo upgrades workflow
set -eu

echo INFO: starting $(basename "$0")

# Exit if not running
if ! pidof ceph-osd &> /dev/null; then
    echo INFO: ceph-osd is not running, skipping
    exit 0
fi

# Exit if not Hammer
INSTALLED_VERSION=$(ceph --version | awk '{print $3}')
if ! [[ "$INSTALLED_VERSION" =~ ^0\.94.* ]]; then
    echo INFO: version of Ceph installed is not 0.94, skipping
    exit 0
fi

OSD_PIDS=$(pidof ceph-osd)
OSD_IDS=$(ls /var/lib/ceph/osd | awk 'BEGIN { FS = "-" } ; { print $2 }')

# "so that mirrors aren't rebalanced as if the OSD died" - gfidente / leseb
ceph osd set noout
ceph osd set norebalance
ceph osd set nodeep-scrub
ceph osd set noscrub

# Stop daemon using Hammer sysvinit script
for OSD_ID in $OSD_IDS; do
    service ceph stop osd.${OSD_ID}
done

# Nice guy will return non-0 only when all failed
timeout 60 bash -c "while kill -0 ${OSD_PIDS} 2> /dev/null; do
  sleep 2;
done"

update_network

# Update (Ceph to Jewel)
yum -y install python-zaqarclient  # needed for os-collect-config
yum -y update

# Restart/Exit if not on Jewel, only in that case we need the changes
UPDATED_VERSION=$(ceph --version | awk '{print $3}')
if [[ "$UPDATED_VERSION" =~ ^0\.94.* ]]; then
    echo WARNING: Ceph was not upgraded, restarting daemon
    for OSD_ID in $OSD_IDS; do
        service ceph start osd.${OSD_ID}
    done
elif [[ "$UPDATED_VERSION" =~ ^10\.2.* ]]; then
    # RPM could own some of these but we can't take risks on the pre-existing files
    for d in /var/lib/ceph/osd /var/log/ceph /var/run/ceph /etc/ceph; do
        chown -L -R ceph:ceph $d || echo WARNING: chown of $d failed
    done

    # Replay udev events with newer rules
    udevadm trigger && udevadm settle

    # If on ext4, we need to enforce lower values for name and namespace len
    # or ceph-osd will refuse to start, see: http://tracker.ceph.com/issues/16187
    for OSD_ID in $OSD_IDS; do
      OSD_FS=$(df -l --output=fstype /var/lib/ceph/osd/ceph-${OSD_ID} | tail -n +2)
      if [ ${OSD_FS} = ext4 ]; then
        crudini --set /etc/ceph/ceph.conf global osd_max_object_name_len 256
        crudini --set /etc/ceph/ceph.conf global osd_max_object_namespace_len 64
      fi
    done

    # Enable systemd unit
    systemctl enable ceph-osd.target
    for OSD_ID in $OSD_IDS; do
        systemctl enable ceph-osd@${OSD_ID}
        systemctl start ceph-osd@${OSD_ID}
    done

    echo INFO: Ceph was upgraded to Jewel
else
    echo ERROR: Ceph was upgraded to an unknown release, daemon is stopped, need manual intervention
    exit 1
fi

ceph osd unset noout
ceph osd unset norebalance
ceph osd unset nodeep-scrub
ceph osd unset noscrub

# From Ceph 10.2.4 we need to set the require_jewel_osds flag when the last OSD
# has been upgraded, see http://ceph.com/geen-categorie/v10-2-4-jewel-released/
if ceph health | grep "all OSDs are running jewel or later"; then
  ceph osd set require_jewel_osds
fi
ENDOFCAT

# ensure the permissions are OK
chmod 0755 $UPGRADE_SCRIPT
