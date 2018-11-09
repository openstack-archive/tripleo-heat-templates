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
# Clear any old environment that may conflict.
for key in \$( set | awk -F= '/^OS_/ {print \$1}' ); do unset "\${key}" ; done

export OS_AUTH_TYPE=password
export OS_PASSWORD=$admin_password
export OS_AUTH_URL=$auth_url
export OS_USERNAME=admin
export OS_PROJECT_NAME=admin
export COMPUTE_API_VERSION=1.1
export NOVA_VERSION=1.1
export OS_NO_CACHE=True
export OS_CLOUDNAME=undercloud
export OS_IDENTITY_API_VERSION='3'
export OS_PROJECT_DOMAIN_NAME='Default'
export OS_USER_DOMAIN_NAME='Default'
EOF_CAT

if [ -n "$internal_tls_ca_file" ]; then
    cat >> $HOMEDIR/stackrc <<-EOF_CAT
export OS_CACERT="$internal_tls_ca_file"
EOF_CAT
fi

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
