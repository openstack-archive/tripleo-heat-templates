#!/bin/bash
set -eux

/sbin/setenforce 0
/sbin/modprobe ebtables

# CentOS sets ptmx to 000. Withoutit being 666, we can't use Cinder volumes
chmod 666 /dev/pts/ptmx

# We need hostname -f to return in a centos container for the puppet hook
HOSTNAME=$(hostname)
echo "127.0.0.1 $HOSTNAME.localdomain $HOSTNAME" >> /etc/hosts

# update docker for local insecure registry(optional)
# Note: This is different for different docker versions
# For older docker versions < 1.4.x use commented line
#echo "OPTIONS='--insecure-registry $docker_registry'" >> /etc/sysconfig/docker
#echo "ADD_REGISTRY='--registry-mirror $docker_registry'" >> /etc/sysconfig/docker

# Local docker registry 1.8
# NOTE(mandre) $docker_namespace_is_registry is not a bash variable but is
# a place holder for text replacement done via heat
if [ "$docker_namespace_is_registry" = True ]; then
    /usr/bin/systemctl stop docker.service
    # if namespace is used with local registry, trim all namespacing
    trim_var=$docker_registry
    registry_host="${trim_var%%/*}"
    /bin/sed -i -r "s/^[# ]*INSECURE_REGISTRY *=.+$/INSECURE_REGISTRY='--insecure-registry $registry_host'/" /etc/sysconfig/docker
    /usr/bin/systemctl start --no-block docker.service
fi

/usr/bin/docker pull $agent_image &
DOCKER_PULL_PID=$!

mkdir -p /var/lib/etc-data/json-config #FIXME: this should be a docker data container

# NOTE(flaper87): Heat Agent required mounts
AGENT_COMMAND_MOUNTS="-v /var/lib/etc-data:/var/lib/etc-data \
                      -v /run:/run \
                      -v /etc:/host/etc \
                      -v /usr/bin/atomic:/usr/bin/atomic \
                      -v /var/lib/dhclient:/var/lib/dhclient \
                      -v /var/lib/cloud:/var/lib/cloud \
                      -v /var/lib/heat-cfntools:/var/lib/heat-cfntools \
                      -v /etc/sysconfig/docker:/etc/sysconfig/docker \
                      -v /usr/lib64/libseccomp.so.2:/usr/lib64/libseccomp.so.2"


# NOTE(flaper87): Some of these commands may not be present depending on the
# atomic version.
for docker_cmd in docker docker-current docker-latest; do
    if [ -f "/usr/bin/$docker_cmd" ]; then
        AGENT_COMMAND_MOUNTS+=" -v /usr/bin/$docker_cmd:/usr/bin/$docker_cmd"
    fi
done

# heat-docker-agents service
cat <<EOF > /etc/systemd/system/heat-docker-agents.service

[Unit]
Description=Heat Docker Agent Container
After=docker.service
Requires=docker.service

[Service]
User=root
Restart=on-failure
ExecStartPre=-/usr/bin/docker kill heat-agents
ExecStartPre=-/usr/bin/docker rm heat-agents
ExecStart=/usr/bin/docker run --name heat-agents --privileged --net=host \
    $AGENT_COMMAND_MOUNTS \
    --entrypoint=/usr/bin/os-collect-config $agent_image
ExecStop=/usr/bin/docker stop heat-agents

[Install]
WantedBy=multi-user.target

EOF

# enable and start heat-docker-agents
chmod 0640 /etc/systemd/system/heat-docker-agents.service
/usr/bin/systemctl enable heat-docker-agents.service
/usr/bin/systemctl start --no-block heat-docker-agents.service

# Disable NetworkManager and let the ifup/down scripts work properly.
/usr/bin/systemctl disable NetworkManager
/usr/bin/systemctl stop NetworkManager

# Atomic's root partition & logical volume defaults to 3G.  In order to launch
# larger VMs, we need to enlarge the root logical volume and scale down the
# docker_pool logical volume. We are allocating 80% of the disk space for
# vm data and the remaining 20% for docker images.
ATOMIC_ROOT='/dev/mapper/atomicos-root'
ROOT_DEVICE=`pvs -o vg_name,pv_name --no-headings | grep atomicos | awk '{ print $2}'`

growpart $( echo "${ROOT_DEVICE}" | sed -r 's/([^0-9]*)([0-9]+)/\1 \2/' )
pvresize "${ROOT_DEVICE}"
lvresize -l +80%FREE "${ATOMIC_ROOT}"
xfs_growfs "${ATOMIC_ROOT}"

cat <<EOF > /etc/sysconfig/docker-storage-setup
GROWPART=true
AUTO_EXTEND_POOL=yes
POOL_AUTOEXTEND_PERCENT=30
POOL_AUTOEXTEND_THRESHOLD=70
EOF

wait $DOCKER_PULL_PID
