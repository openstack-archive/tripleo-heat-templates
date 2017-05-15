#!/bin/bash
set -eux

# TODO remove this when built image includes docker
if [ ! -f "/usr/bin/docker" ]; then
    yum -y install docker
fi

# Local docker registry 1.8
# NOTE(mandre) $docker_namespace_is_registry is not a bash variable but is
# a place holder for text replacement done via heat
if [ "$docker_namespace_is_registry" = "True" ]; then
    /usr/bin/systemctl stop docker.service
    # if namespace is used with local registry, trim all namespacing
    trim_var=$docker_registry
    registry_host="${trim_var%%/*}"
    /bin/sed -i -r "s/^[# ]*INSECURE_REGISTRY *=.+$/INSECURE_REGISTRY='--insecure-registry $registry_host'/" /etc/sysconfig/docker
fi

mkdir -p /var/lib/etc-data/json-config #FIXME: this should be a docker data container

# NOTE(flaper87): Heat Agent required mounts
AGENT_COMMAND_MOUNTS="\
-v /var/lib/etc-data:/var/lib/etc-data \
-v /run:/run \
-v /etc/hosts:/etc/hosts \
-v /etc:/host/etc \
-v /var/lib/dhclient:/var/lib/dhclient \
-v /var/lib/cloud:/var/lib/cloud \
-v /var/lib/heat-cfntools:/var/lib/heat-cfntools \
-v /var/lib/os-collect-config:/var/lib/os-collect-config \
-v /var/lib/os-apply-config-deployments:/var/lib/os-apply-config-deployments \
-v /var/lib/heat-config:/var/lib/heat-config \
-v /etc/sysconfig/docker:/etc/sysconfig/docker \
-v /etc/sysconfig/network-scripts:/etc/sysconfig/network-scripts \
-v /usr/lib64/libseccomp.so.2:/usr/lib64/libseccomp.so.2 \
-v /usr/bin/docker:/usr/bin/docker \
-v /usr/bin/docker-current:/usr/bin/docker-current \
-v /var/lib/os-collect-config:/var/lib/os-collect-config \
-v /etc/ssh:/etc/ssh"

# heat-docker-agents service
cat <<EOF > /etc/systemd/system/heat-docker-agents.service
[Unit]
Description=Heat Docker Agent Container
After=docker.service
Requires=docker.service
Before=os-collect-config.service
Conflicts=os-collect-config.service

[Service]
User=root
Restart=always
ExecStartPre=-/usr/bin/docker rm -f heat-agents
ExecStart=/usr/bin/docker run --name heat-agents --privileged --net=host \
    $AGENT_COMMAND_MOUNTS \
    --entrypoint=/usr/bin/os-collect-config $agent_image
ExecStop=/usr/bin/docker stop heat-agents

[Install]
WantedBy=multi-user.target
EOF

# enable and start heat-docker-agents
/usr/bin/systemctl enable heat-docker-agents.service
/usr/bin/systemctl start --no-block heat-docker-agents.service

# Disable libvirtd
/usr/bin/systemctl disable libvirtd.service
/usr/bin/systemctl stop libvirtd.service
