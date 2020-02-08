#!/bin/bash
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

set -e
[ "$DEBUG" = "false" ] || set -x
mkdir -p /etc/puppet
cp -dR /tmp/puppet-etc/* /etc/puppet
rm -Rf /etc/puppet/ssl # not in use and causes permission errors
echo "{\"step\": $STEP}" > /etc/puppet/hieradata/docker_puppet.json
TAGS=""
if [ -n "$PUPPET_TAGS" ]; then
    TAGS="--tags \"$PUPPET_TAGS\""
fi

CHECK_MODE=""
if [ -d "/tmp/puppet-check-mode" ]; then
    mkdir -p /etc/puppet/check-mode
    cp -a /tmp/puppet-check-mode/* /etc/puppet/check-mode
    CHECK_MODE="--hiera_config /etc/puppet/check-mode/hiera.yaml"
fi

# Create a reference timestamp to easily find all files touched by
# puppet. The sync ensures we get all the files we want due to
# different timestamp.
conf_data_path="/var/lib/config-data/${NAME}"
origin_of_time="${conf_data_path}.origin_of_time"
touch $origin_of_time
sync

export NET_HOST="${NET_HOST:-false}"
set +e
if [ "$NET_HOST" == "false" ]; then
    export FACTER_hostname=$HOSTNAME
fi
# $::deployment_type in puppet-tripleo
export FACTER_deployment_type=containers
export FACTER_uuid=$(cat /sys/class/dmi/id/product_uuid | tr '[:upper:]' '[:lower:]')
echo 'Running puppet'
# FIXME(bogdando): stdout may be falling behind of the logged syslog messages
set -x
/usr/bin/puppet apply --summarize \
                      --detailed-exitcodes \
                      --color=false \
                      --modulepath=/etc/puppet/modules:/usr/share/openstack-puppet/modules \
                      $TAGS \
                      $CHECK_MODE \
                      /etc/config.pp \
                      2>&1 | logger -s -t puppet-user
rc=${PIPESTATUS[0]}
[ "$DEBUG" = "false" ] && set +x
set -e
if [ $rc -ne 2 -a $rc -ne 0 ]; then
    exit $rc
fi

verbosity=""
[ "$DEBUG" = "false" ] || verbosity="-v"

# Disables archiving
if [ -z "$NO_ARCHIVE" ]; then
    archivedirs=("/etc" "/root" "/opt" "/var/lib/ironic/tftpboot" "/var/lib/ironic/httpboot" "/var/www" "/var/spool/cron" "/var/lib/nova/.ssh")
    rsync_srcs=""
    for d in "${archivedirs[@]}"; do
        if [ -d "$d" ]; then
            rsync_srcs+=" $d"
        fi
    done
    # On stack update, if a password was changed in a config file,
    # some services (e.g. mysql) must change their internal state
    # (e.g. password in mysql DB) when paunch restarts them; and
    # they need the old password to achieve that.
    # For those services, we update the config hash to notify
    # paunch that a restart is needed, but we do not update the
    # password file in container-puppet if the file already existed
    # before and let the service regenerate it instead.
    password_files="/root/.my.cnf"

    exclude_files=""
    for p in $password_files; do
        if [ -f "$p" -a -f "${conf_data_path}$p" ]; then
            exclude_files+=" --exclude=$p"
        fi
    done

    # Exclude read-only mounted directories/files which we do not want
    # to copy or delete.
    ro_files="/etc/puppetlabs/ /opt/puppetlabs/"
    for ro in $ro_files; do
        if [ -e "$ro" ]; then
            exclude_files+=" --exclude=$ro"
        fi
    done

    echo "Evaluating config files to be removed for the $NAME configuration"
    TMPFILE=$(mktemp /tmp/tmp.XXXXXXXXXX)
    TMPFILE2=$(mktemp /tmp/tmp.XXXXXXXXXX)
    trap 'rm -rf $TMPFILE $TMPFILE2' EXIT INT HUP
    rsync -av -R --dry-run --delete-after $exclude_files $rsync_srcs ${conf_data_path} |\
        awk '/^deleting/ {print $2}' > $TMPFILE

    echo "Rsyncing config files from ${rsync_srcs} into ${conf_data_path}"
    rsync -a $verbosity -R --delay-updates --delete-after $exclude_files $rsync_srcs ${conf_data_path}


    # Also make a copy of files modified during puppet run
    echo "Gathering files modified after $(stat -c '%y' $origin_of_time)"

    # Purge obsoleted contents to maintain a fresh and filtered mirror
    puppet_generated_path=/var/lib/config-data/puppet-generated/${NAME}
    mkdir -p ${puppet_generated_path}
    echo "Ensuring the removed config files are also purged in ${puppet_generated_path}:"
    cat $TMPFILE | sort
    cat $TMPFILE | xargs -n1 -r -I{} \
        bash -c "rm -rf ${puppet_generated_path}/{}"
    exec 5>&1
    exec 1>$TMPFILE2
    find $rsync_srcs -newer $origin_of_time -not -path '/etc/puppet*' -print0
    exec 1>&5
    echo "Files modified during puppet run:"
    cat $TMPFILE2 | xargs -0 printf "%s\n" | sort -h
    echo "Rsyncing the modified files into ${puppet_generated_path}"
    rsync -a $verbosity -R -0 --delay-updates --delete-after $exclude_files \
        --files-from=$TMPFILE2 / ${puppet_generated_path}

    # Write a checksum of the config-data dir, this is used as a
    # salt to trigger container restart when the config changes
    # note: while being excluded from the output, password files
    # are still included in checksum computation
    additional_checksum_files=""
    excluded_original_passwords=""
    for p in $password_files; do
        if [ -f "$p" ]; then
            additional_checksum_files+=" $p"
            excluded_original_passwords+=" --exclude=/var/lib/config-data/*${p}"
        fi
    done
    # We need to exclude the swift ring backups as those change over time and
    # containers do not need to restart if they change
    EXCLUDE=--exclude='*/etc/swift/backups/*'\ --exclude='*/etc/libvirt/passwd.db'\ ${excluded_original_passwords}

    # We need to repipe the tar command through 'tar xO' to force text
    # output because otherwise the sed command cannot work. The sed is
    # needed because puppet puts timestamps as comments in cron and
    # parsedfile resources, hence triggering a change at every redeploy
    tar -c --mtime='1970-01-01' $EXCLUDE -f - ${conf_data_path} $additional_checksum_files | tar xO | \
            sed '/^#.*HEADER.*/d' | md5sum | awk '{print $1}' > ${conf_data_path}.md5sum
    tar -c --mtime='1970-01-01' $EXCLUDE -f - ${puppet_generated_path} $additional_checksum_files --mtime='1970-01-01' | tar xO \
            | sed '/^#.*HEADER.*/d' | md5sum | awk '{print $1}' > ${puppet_generated_path}.md5sum
fi
