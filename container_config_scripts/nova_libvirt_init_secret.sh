#!/bin/bash

set -e

CEPH_INFO=($*)

if [ -z "$CEPH_INFO" ]; then
    echo "error: At least one CLUSTER:CLIENT tuple must be specified"
    exit 1
fi

echo "------------------------------------------------"
echo "Initializing virsh secrets for: ${CEPH_INFO[@]}"

for INFO in ${CEPH_INFO[@]}; do
    IFS=: read CLUSTER CLIENT <<< $INFO
    FSID=$(awk '$1 == "fsid" {print $3}' /etc/ceph/${CLUSTER}.conf)

    echo "--------"
    echo "Initializing the virsh secret for '$CLUSTER' cluster ($FSID) '$CLIENT' client"

    # Ensure the secret XML file exists. Puppet should have created a secret.xml
    # file for the first cluster's secret, so detect when to use that file.
    if grep -q $FSID /etc/nova/secret.xml; then
        SECRET_FILE="/etc/nova/secret.xml"
        SECRET_NAME="client.${CLIENT} secret"
    else
        SECRET_FILE="/etc/nova/${CLUSTER}-secret.xml"
        SECRET_NAME="${CLUSTER}.client.${CLIENT} secret"
    fi

    if [ ! -f $SECRET_FILE ]; then
        echo "Creating $SECRET_FILE"
        cat <<EOF > $SECRET_FILE
<secret ephemeral='no' private='no'>
  <usage type='ceph'>
    <name>${SECRET_NAME}</name>
  </usage>
  <uuid>${FSID}</uuid>
</secret>
EOF
    else
        echo "The $SECRET_FILE file already exists"
    fi

    # Ensure the libvirt secret is defined
    if /usr/bin/virsh secret-list | grep -q $FSID; then
        echo "The virsh secret for $FSID has already been defined"
    else
        /usr/bin/virsh secret-define --file $SECRET_FILE
    fi

    # Fetch the key from the keyring and ensure the secret is set
    KEY=$(awk '$1 == "key" {print $3}' /etc/ceph/${CLUSTER}.client.${CLIENT}.keyring)
    if /usr/bin/virsh secret-get-value $FSID 2>/dev/null | grep -q $KEY; then
        echo "The virsh secret for $FSID has already been set"
    else
        /usr/bin/virsh secret-set-value --secret $FSID --base64 $KEY
    fi
done
