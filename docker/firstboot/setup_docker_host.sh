#!/bin/bash
set -eux
# TODO This would be better in puppet

# TODO remove this when built image includes docker
if [ ! -f "/usr/bin/docker" ]; then
    yum -y install docker
fi

# NOTE(mandre) $docker_namespace_is_registry is not a bash variable but is
# a place holder for text replacement done via heat
if [ "$docker_namespace_is_registry" = "True" ]; then
    /usr/bin/systemctl stop docker.service
    # if namespace is used with local registry, trim all namespacing
    trim_var=$docker_registry
    registry_host="${trim_var%%/*}"
    /bin/sed -i -r "s/^[# ]*INSECURE_REGISTRY *=.+$/INSECURE_REGISTRY='--insecure-registry $registry_host'/" /etc/sysconfig/docker
fi

# enable and start docker
/usr/bin/systemctl enable docker.service
/usr/bin/systemctl start docker.service

# Disable libvirtd
/usr/bin/systemctl disable libvirtd.service
/usr/bin/systemctl stop libvirtd.service
