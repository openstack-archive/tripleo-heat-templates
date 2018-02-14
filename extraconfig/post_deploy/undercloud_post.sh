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

. $HOMEDIR/stackrc

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

if [ "$(hiera nova_api_enabled)" = "true" ]; then
    # Disable nova quotas
    openstack quota set --cores -1 --instances -1 --ram -1 $(openstack project show admin | awk '$2=="id" {print $4}')

  # Configure flavors.
  RESOURCES='--property resources:CUSTOM_BAREMETAL=1 --property resources:DISK_GB=0 --property resources:MEMORY_MB=0 --property resources:VCPU=0 --property capabilities:boot_option=local'
  SIZINGS='--ram 4096 --vcpus 1 --disk 40'

  if ! openstack flavor show baremetal >/dev/null 2>&1; then
      openstack flavor create $SIZINGS $RESOURCES baremetal
  fi
  if ! openstack flavor show control >/dev/null 2>&1; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=control control
  fi
  if ! openstack flavor show compute >/dev/null 2>&1; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=compute compute
  fi
  if ! openstack flavor show ceph-storage >/dev/null 2>&1; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=ceph-storage ceph-storage
  fi
  if ! openstack flavor show block-storage >/dev/null 2>&1; then
      openstack flavor create $SIZINGS $RESOURCES --property capabilities:profile=block-storage block-storage
  fi
  if ! openstack flavor show swift-storage >/dev/null 2>&1; then
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
    openstack keypair create --public-key $HOMEDIR/.ssh/id_rsa.pub 'default'
fi

# MISTRAL WORKFLOW CONFIGURATION
if [ "$(hiera mistral_api_enabled)" = "true" ]; then
    echo Configuring Mistral workbooks.
    for workbook in $(openstack workbook list | grep tripleo | cut -f 2 -d ' '); do
        openstack workbook delete $workbook
    done
    if openstack cron trigger show publish-ui-logs-hourly >/dev/null 2>&1; then
        openstack cron trigger delete publish-ui-logs-hourly
    fi
    #TODO In the future we should be able to run something like
    # openstack workflow list --filter=tag=tripleo-common-managed
    # but right now this is broken in Mistral, so we'll fix later.
    for workflow in $(openstack workflow list -c Name -c Tags | grep tripleo-common-managed); do
        NAME=$(echo ${workflow} | awk '{print $2}')
        TAG=$(echo ${workflow} | awk '{print $4}')
        if echo $TAG | grep -q tripleo-common-managed; then
            openstack workflow delete $NAME
        fi
    done
    for workbook in $(ls /usr/share/openstack-tripleo-common/workbooks/*); do
        openstack workbook create $workbook
    done
    openstack cron trigger create publish-ui-logs-hourly tripleo.plan_management.v1.publish_ui_logs_to_swift --pattern '0 * * * *'
    echo Mistral workbooks configured successfully.

  # Store the SNMP password in a mistral environment
  if ! openstack workflow env show tripleo.undercloud-config >/dev/null 2>&1; then
      TMP_MISTRAL_ENV=$(mktemp)
      echo "{\"name\": \"tripleo.undercloud-config\", \"variables\": {\"undercloud_ceilometer_snmpd_password\": \"$snmp_readonly_user_password\"}}" > $TMP_MISTRAL_ENV
      echo Configure Mistral environment with undercloud-config
      openstack workflow env create $TMP_MISTRAL_ENV
  fi

  if [ "$(hiera enable_validations)" = "true" ]; then
      echo Execute copy_ssh_key validations
      openstack workflow execution create tripleo.validations.v1.copy_ssh_key
  fi
fi
