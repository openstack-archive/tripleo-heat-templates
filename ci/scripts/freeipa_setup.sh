#!/bin/bash
#
# Used environment variables:
#
#   - Hostname
#   - FreeIPAIP
#   - DirectoryManagerPassword
#   - AdminPassword
#   - UndercloudFQDN
#   - HostsSecret
#   - ProvisioningCIDR: If set, it adds the given CIDR to the provisioning
#                       interface (which is hardcoded to eth1)
#   - FreeIPAExtraArgs: Additional parameters to be passed to FreeIPA script
#
set -eux

if [ -f "~/freeipa-setup.env" ]; then
    source ~/freeipa-setup.env
elif [ -f "/tmp/freeipa-setup.env" ]; then
    source /tmp/freeipa-setup.env
fi

export Hostname=${Hostname:-""}
export FreeIPAIP=${FreeIPAIP:-""}
export DirectoryManagerPassword=${DirectoryManagerPassword:-""}
export AdminPassword=${AdminPassword:-""}
export UndercloudFQDN=${UndercloudFQDN:-""}
export HostsSecret=${HostsSecret:-""}
export ProvisioningCIDR=${ProvisioningCIDR:-""}
export FreeIPAExtraArgs=${FreeIPAExtraArgs:-""}

if [ -n "$ProvisioningCIDR" ]; then
    # Add address to provisioning network interface
    ip link set dev eth1 up
    ip addr add $ProvisioningCIDR dev eth1
fi

# Set DNS servers
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

if rpm -q openstack-dashboard; then
    yum -q -y remove openstack-dashboard
fi

source /etc/os-release
# RHEL8.0 does not have epel yet
if [[ $VERSION_ID == 8* ]]; then
    PKGS="ipa-server ipa-server-dns rng-tools git"
else
    PKGS="ipa-server ipa-server-dns epel-release rng-tools mod_nss git haveged"
fi

# Install the needed packages
yum -q install -y $PKGS

# Prepare hostname
hostnamectl set-hostname --static $Hostname

echo $FreeIPAIP `hostname` | tee -a /etc/hosts

# Set iptables rules
cat << EOF > freeipa-iptables-rules.txt
# Firewall configuration written by system-config-firewall
# Manual customization of this file is not recommended.
*filter
:INPUT ACCEPT [0:0]
:FORWARD ACCEPT [0:0]
:OUTPUT ACCEPT [0:0]
-A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
-A INPUT -p icmp -j ACCEPT
-A INPUT -i lo -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 22 -j ACCEPT
#TCP ports for FreeIPA
-A INPUT -m state --state NEW -m tcp -p tcp --dport 80 -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 443  -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 389 -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 636 -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 88  -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 464  -j ACCEPT
-A INPUT -m state --state NEW -m tcp -p tcp --dport 53  -j ACCEPT
#UDP ports for FreeIPA
-A INPUT -m state --state NEW -m udp -p udp --dport 88 -j ACCEPT
-A INPUT -m state --state NEW -m udp -p udp --dport 464 -j ACCEPT
-A INPUT -m state --state NEW -m udp -p udp --dport 123 -j ACCEPT
-A INPUT -m state --state NEW -m udp -p udp --dport 53 -j ACCEPT
-A INPUT -j REJECT --reject-with icmp-host-prohibited
-A FORWARD -j REJECT --reject-with icmp-host-prohibited
COMMIT
EOF

iptables-restore < freeipa-iptables-rules.txt

# Entropy generation; otherwise, ipa-server-install will lag.
if [[ $VERSION_ID != 8* ]]; then
   chkconfig haveged on
   systemctl start haveged

   # Remove conflicting httpd configuration
   rm -f /etc/httpd/conf.d/ssl.conf
fi

# Set up FreeIPA
ipa-server-install -U -r `hostname -d|tr "[a-z]" "[A-Z]"` \
                   -p $DirectoryManagerPassword -a $AdminPassword \
                   --hostname `hostname -f` \
                   --ip-address=$FreeIPAIP \
                   --allow-zone-overlap \
                   --setup-dns --auto-forwarders --auto-reverse $FreeIPAExtraArgs

# Authenticate
echo $AdminPassword | kinit admin

# Verify we have TGT
klist

if [ "$?" = '1' ]; then
    exit 1
fi
