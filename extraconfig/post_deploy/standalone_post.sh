#!/bin/bash
set -eux

ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml

HOMEDIR="$homedir"

# write out clouds.yaml

mkdir -p $HOMEDIR/.config/openstack
touch $HOMEDIR/.config/openstack/clouds.yaml
chown 600 $HOMEDIR/.config/openstack/clouds.yaml
cat <<EOF >$HOMEDIR/.config/openstack/clouds.yaml
clouds:
  $cloud_name:
    auth:
      auth_url: $auth_url
      project_name: admin
      username: admin
      password: $admin_password
    region_name: $region_name
    identity_api_version: 3
    cloud: standalone
EOF


