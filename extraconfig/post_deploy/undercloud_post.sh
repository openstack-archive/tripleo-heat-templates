#!/bin/bash
set -eux

ln -sf /etc/puppet/hiera.yaml /etc/hiera.yaml

HOMEDIR="$homedir"
USERNAME=`ls -ld $HOMEDIR | awk {'print $3'}`
GROUPNAME=`ls -ld $HOMEDIR | awk {'print $4'}`

# WRITE OUT STACKRC
touch $HOMEDIR/stackrc
chmod 0600 $HOMEDIR/stackrc

cat > $HOMEDIR/stackrc <<-EOF_CAT
export OS_AUTH_TYPE=password
export OS_PASSWORD=$admin_password
export OS_AUTH_URL=$auth_url
export OS_USERNAME=admin
export OS_PROJECT_NAME=admin
export COMPUTE_API_VERSION=1.1
export NOVA_VERSION=1.1
export OS_NO_CACHE=True
export OS_CLOUDNAME=undercloud
# 1.34 is the latest API version in Ironic Pike supported by ironicclient
export IRONIC_API_VERSION=1.34
export OS_BAREMETAL_API_VERSION=\$IRONIC_API_VERSION
export OS_IDENTITY_API_VERSION='3'
export OS_PROJECT_DOMAIN_NAME='Default'
export OS_USER_DOMAIN_NAME='Default'
EOF_CAT

cat >> $HOMEDIR/stackrc <<-"EOF_CAT"
# Add OS_CLOUDNAME to PS1
if [ -z "${CLOUDPROMPT_ENABLED:-}" ]; then
    export PS1=${PS1:-""}
    export PS1=\${OS_CLOUDNAME:+"(\$OS_CLOUDNAME)"}\ $PS1
    export CLOUDPROMPT_ENABLED=1
fi
EOF_CAT

if [ -n "$ssl_certificate" ]; then
    cat >> $HOMEDIR/stackrc <<-EOF_CAT
export PYTHONWARNINGS="ignore:Certificate has no, ignore:A true SSLContext object is not available"
EOF_CAT
fi

chown "$USERNAME:$GROUPNAME" "$HOMEDIR/stackrc"

source $HOMEDIR/stackrc

if [ ! -f $HOMEDIR/.ssh/authorized_keys ]; then
    sudo mkdir -p $HOMEDIR/.ssh
    sudo chmod 700 $HOMEDIR/.ssh/
    sudo touch $HOMEDIR/.ssh/authorized_keys
    sudo chmod 600 $HOMEDIR/.ssh/authorized_keys
fi

if [ ! -f $HOMEDIR/.ssh/id_rsa ]; then
    ssh-keygen -b 1024 -N '' -f $HOMEDIR/.ssh/id_rsa
fi

if ! grep "$(cat $HOMEDIR/.ssh/id_rsa.pub)" $HOMEDIR/.ssh/authorized_keys; then
    cat $HOMEDIR/.ssh/id_rsa.pub >> $HOMEDIR/.ssh/authorized_keys
fi
chown -R "$USERNAME:$GROUPNAME" "$HOMEDIR/.ssh"

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
            $NAMESERVER_ARG ctlplane-subnet
    fi
fi

if [ "$(hiera nova_api_enabled)" = "true" ]; then
    # Disable nova quotas
    openstack quota set --cores -1 --instances -1 --ram -1 $(openstack project show admin | awk '$2=="id" {print $4}')

  # Configure flavors.
  RESOURCES='--property resources:CUSTOM_BAREMETAL=1 --property resources:DISK_GB=0 --property resources:MEMORY_MB=0 --property resources:VCPU=0 --property capabilities:boot_option=local'
  SIZINGS='--ram 4096 --vcpus 1 --disk 40'

  if ! openstack flavor show baremetal &> /dev/null; then
      openstack flavor create $SIZINGS $RESOURCES baremetal
  fi
  if ! openstack flavor show control &> /dev/null; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=control control
  fi
  if ! openstack flavor show compute &> /dev/null; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=compute compute
  fi
  if ! openstack flavor show ceph-storage &> /dev/null; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=ceph-storage ceph-storage
  fi
  if ! openstack flavor show block-storage &> /dev/null; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=block-storage block-storage
  fi
  if ! openstack flavor show swift-storage &> /dev/null; then
    openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=swift-storage swift-storage
  fi
fi

# Set up a default keypair.
if [ ! -e $HOMEDIR/.ssh/id_rsa ]; then
    sudo -E -u $USERNAME ssh-keygen -t rsa -N '' -f $HOMEDIR/.ssh/id_rsa
fi

if openstack keypair show default; then
    echo Keypair already exists.
else
    echo Creating new keypair.
    openstack keypair create 'default' < $HOMEDIR/.ssh/id_rsa.pub
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
