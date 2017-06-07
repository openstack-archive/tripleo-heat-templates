#!/bin/bash
set -eux

ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml


# WRITE OUT STACKRC
if [ ! -e /root/stackrc ]; then
    touch /root/stackrc
    chmod 0600 /root/stackrc

cat >> /root/stackrc <<-EOF_CAT
export OS_PASSWORD=$admin_password
export OS_AUTH_URL=$auth_url
export OS_USERNAME=admin
export OS_TENANT_NAME=admin
export COMPUTE_API_VERSION=1.1
export NOVA_VERSION=1.1
export OS_BAREMETAL_API_VERSION=1.15
export OS_NO_CACHE=True
export OS_CLOUDNAME=undercloud
EOF_CAT

    if [ -n "$ssl_certificate" ]; then
cat >> /root/stackrc <<-EOF_CAT
export PYTHONWARNINGS="ignore:Certificate has no, ignore:A true SSLContext object is not available"
EOF_CAT
    fi
fi

source /root/stackrc

if [ ! -f /root/.ssh/authorized_keys ]; then
    sudo mkdir -p /root/.ssh
    sudo chmod 7000 /root/.ssh/
    sudo touch /root/.ssh/authorized_keys
    sudo chmod 600 /root/.ssh/authorized_keys
fi

if [ ! -f /root/.ssh/id_rsa ]; then
    ssh-keygen -b 1024 -N '' -f /root/.ssh/id_rsa
fi

if ! grep "$(cat /root/.ssh/id_rsa.pub)" /root/.ssh/authorized_keys; then
    cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys
fi

if [ "$(hiera neutron_api_enabled)" = "true" ]; then
    PHYSICAL_NETWORK=ctlplane

    ctlplane_id=$(openstack network list -f csv -c ID -c Name --quote none | tail -n +2 | grep ctlplane | cut -d, -f1)
    subnet_ids=$(openstack subnet list -f csv -c ID --quote none | tail -n +2)
    subnet_id=

    for subnet_id in $subnet_ids; do
        network_id=$(openstack subnet show -f value -c network_id $subnet_id)
        if [ "$network_id" = "$ctlplane_id" ]; then
            break
        fi
    done

    net_create=1
    if [ -n "$subnet_id" ]; then
        cidr=$(openstack subnet show $subnet_id -f value -c cidr)
        if [ "$cidr" = "$undercloud_network_cidr" ]; then
            net_create=0
        else
            echo "New cidr $undercloud_network_cidr does not equal old cidr $cidr"
            echo "Will attempt to delete and recreate subnet $subnet_id"
        fi
    fi

    if [ "$net_create" -eq "1" ]; then
        # Delete the subnet and network to make sure it doesn't already exist
        if openstack subnet list | grep start; then
            openstack subnet delete $(openstack subnet list | grep start | awk '{print $4}')
        fi
        if openstack network show ctlplane; then
            openstack network delete ctlplane
        fi


        NETWORK_ID=$(openstack network create --provider-network-type=flat --provider-physical-network=ctlplane ctlplane | grep " id " | awk '{print $4}')

        NAMESERVER_ARG=""
        if [ -n "${undercloud_nameserver:-}" ]; then
            NAMESERVER_ARG="--dns-nameserver $undercloud_nameserver"
        fi

        openstack subnet create --network=$NETWORK_ID \
            --gateway=$undercloud_network_gateway \
            --subnet-range=$undercloud_network_cidr \
            --allocation-pool start=$undercloud_dhcp_start,end=$undercloud_dhcp_end \
            --host-route destination=169.254.169.254/32,gateway=$local_ip \
            $NAMESERVER_ARG ctlplane
    fi
fi

if [ "$(hiera nova_api_enabled)" = "true" ]; then
    # Disable nova quotas
    openstack quota set --cores -1 --instances -1 --ram -1 $(openstack project show admin | awk '$2=="id" {print $4}')
fi

# MISTRAL WORKFLOW CONFIGURATION
if [ "$(hiera mistral_api_enabled)" = "true" ]; then
    # load workflows
    for workbook in $(openstack workbook list | grep tripleo | cut -f 2 -d ' '); do
        openstack workbook delete $workbook
    done
    for workflow in $(openstack workflow list | grep tripleo | cut -f 2 -d ' '); do
        openstack workflow delete $workflow
    done
    for workbook in $(ls /usr/share/openstack-tripleo-common/workbooks/*); do
        openstack workbook create $workbook
    done

  # Store the SNMP password in a mistral environment
  if ! openstack workflow env show tripleo.undercloud-config &>/dev/null; then
      TMP_MISTRAL_ENV=$(mktemp)
      echo "{\"name\": \"tripleo.undercloud-config\", \"variables\": {\"undercloud_ceilometer_snmpd_password\": \"$snmp_readonly_user_password\"}}" > $TMP_MISTRAL_ENV
      openstack workflow env create $TMP_MISTRAL_ENV
   fi

fi

# IP forwarding is needed to allow the overcloud nodes access to the outside
# internet in cases where they are on an isolated network.
sysctl -w net.ipv4.ip_forward=1
# Make it persistent
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/ip-forward.conf
