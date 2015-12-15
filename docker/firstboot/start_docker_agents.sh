#!/bin/bash
set -eux

# firstboot isn't split out by role yet so we handle it this way
if ! hostname | grep compute &>/dev/null; then
 echo "Exiting. This script is only for the compute role."
 exit 0
fi

mkdir -p /var/lib/etc-data/json-config #FIXME: this should be a docker data container

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
ExecStartPre=/usr/bin/docker pull $agent_image
ExecStart=/usr/bin/docker run --name heat-agents --privileged --net=host -v /var/lib/etc-data:/var/lib/etc-data -v /run:/run -v /etc:/host/etc -v /usr/bin/atomic:/usr/bin/atomic -v /var/lib/dhclient:/var/lib/dhclient -v /var/lib/cloud:/var/lib/cloud -v /var/lib/heat-cfntools:/var/lib/heat-cfntools --entrypoint=/usr/bin/os-collect-config $agent_image
ExecStop=/usr/bin/docker stop heat-agents

[Install]
WantedBy=multi-user.target

EOF

# update docker for local insecure registry(optional)
# Note: This is different for different docker versions
# For older docker versions < 1.4.x use commented line
#echo "OPTIONS='--insecure-registry $docker_registry'" >> /etc/sysconfig/docker
#echo "ADD_REGISTRY='--registry-mirror $docker_registry'" >> /etc/sysconfig/docker

# Local docker registry 1.8
if [ $docker_namespace_is_registry ]; then
    /bin/sed -i "s/# INSECURE_REGISTRY='--insecure-registry '/INSECURE_REGISTRY='--insecure-registry $docker_registry'/g" /etc/sysconfig/docker
fi

/sbin/setenforce 0
/sbin/modprobe ebtables

echo nameserver 8.8.8.8 > /etc/resolv.conf

# We need hostname -f to return in a centos container for the puppet hook
HOSTNAME=$(hostname)
echo "127.0.0.1 $HOSTNAME.localdomain $HOSTNAME" >> /etc/hosts

# Another hack.. we need latest docker..
/usr/bin/systemctl stop docker.service
/bin/curl -o /tmp/docker https://get.docker.com/builds/Linux/x86_64/docker-latest
/bin/mount -o remount,rw /usr
/bin/rm /bin/docker
/bin/cp /tmp/docker /bin/docker
/bin/chmod 755 /bin/docker

# enable and start docker
/usr/bin/systemctl enable docker.service
/usr/bin/systemctl restart --no-block docker.service

# enable and start heat-docker-agents
chmod 0640 /etc/systemd/system/heat-docker-agents.service
/usr/bin/systemctl enable heat-docker-agents.service
/usr/bin/systemctl start --no-block heat-docker-agents.service

# Disable NetworkManager and let the ifup/down scripts work properly.
/usr/bin/systemctl disable NetworkManager
/usr/bin/systemctl stop NetworkManager
