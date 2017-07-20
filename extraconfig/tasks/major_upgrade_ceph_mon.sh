#!/bin/bash
set -eu
set -o pipefail

echo INFO: starting $(basename "$0")

# Exit if not running
if ! pidof ceph-mon &> /dev/null; then
    echo INFO: ceph-mon is not running, skipping
    exit 0
fi

# Exit if not Hammer
INSTALLED_VERSION=$(ceph --version | awk '{print $3}')
if ! [[ "$INSTALLED_VERSION" =~ ^0\.94.* ]]; then
    echo INFO: version of Ceph installed is not 0.94, skipping
    exit 0
fi

CEPH_STATUS=$(ceph health | awk '{print $1}')
if [ ${CEPH_STATUS} = HEALTH_ERR ]; then
    echo ERROR: Ceph cluster status is HEALTH_ERR, cannot be upgraded
    exit 1
fi

# Useful when upgrading with OSDs num < replica size
if [[ ${ignore_ceph_upgrade_warnings:-False} != [Tt]rue ]]; then
    timeout 300 bash -c "while [ ${CEPH_STATUS} != HEALTH_OK ]; do
      echo WARNING: Waiting for Ceph cluster status to go HEALTH_OK;
      sleep 30;
      CEPH_STATUS=$(ceph health | awk '{print $1}')
    done"
fi

MON_PID=$(pidof ceph-mon)
MON_ID=$(hostname -s)

# Stop daemon using Hammer sysvinit script
service ceph stop mon.${MON_ID}

# Ensure it's stopped
timeout 60 bash -c "while kill -0 ${MON_PID} 2> /dev/null; do
  sleep 2;
done"

# Update to Jewel
yum -y -q update ceph-mon ceph

# Restart/Exit if not on Jewel, only in that case we need the changes
UPDATED_VERSION=$(ceph --version | awk '{print $3}')
if [[ "$UPDATED_VERSION" =~ ^0\.94.* ]]; then
    echo WARNING: Ceph was not upgraded, restarting daemons
    service ceph start mon.${MON_ID}
elif [[ "$UPDATED_VERSION" =~ ^10\.2.* ]]; then
    # RPM could own some of these but we can't take risks on the pre-existing files
    for d in /var/lib/ceph/mon /var/log/ceph /var/run/ceph /etc/ceph; do
        chown -L -R ceph:ceph $d || echo WARNING: chown of $d failed
    done

    # Replay udev events with newer rules
    udevadm trigger

    # Enable systemd unit
    systemctl enable ceph-mon.target
    systemctl enable ceph-mon@${MON_ID}
    systemctl start ceph-mon@${MON_ID}

    # Wait for daemon to be back in the quorum
    timeout 300 bash -c "until (ceph quorum_status | jq .quorum_names | grep -sq ${MON_ID}); do
      echo WARNING: Waiting for mon.${MON_ID} to re-join quorum;
      sleep 10;
    done"

    # if tunables become legacy, cluster status will be HEALTH_WARN causing
    # upgrade to fail on following node
    ceph osd crush tunables default

    echo INFO: Ceph was upgraded to Jewel
else
    echo ERROR: Ceph was upgraded to an unknown release, daemon is stopped, need manual intervention
    exit 1
fi
