#!/bin/bash

set -eu

check_cluster()
{
    if pcs status 2>&1 | grep -E '(cluster is not currently running)|(OFFLINE:)'; then
        echo_error "ERROR: upgrade cannot start with some cluster nodes being offline"
        exit 1
    fi
}

check_pcsd()
{
    if pcs status 2>&1 | grep -E 'Offline'; then
        echo_error "ERROR: upgrade cannot start with some pcsd daemon offline"
        exit 1
    fi
}

check_disk_for_mysql_dump()
{
    # Where to backup current database if mysql need to be upgraded
    MYSQL_BACKUP_DIR=/var/tmp/mysql_upgrade_osp
    MYSQL_TEMP_UPGRADE_BACKUP_DIR=/var/lib/mysql-temp-upgrade-backup
    # Spare disk ratio for extra safety
    MYSQL_BACKUP_SIZE_RATIO=1.2

    # Shall we upgrade mysql data directory during the stack upgrade?
    if [ "$mariadb_do_major_upgrade" = "auto" ]; then
        ret=$(is_mysql_upgrade_needed)
        if [ $ret = "1" ]; then
            DO_MYSQL_UPGRADE=1
        else
            DO_MYSQL_UPGRADE=0
        fi
        echo "mysql upgrade required: $DO_MYSQL_UPGRADE"
    elif [ "$mariadb_do_major_upgrade" = "no" ]; then
        DO_MYSQL_UPGRADE=0
    else
        DO_MYSQL_UPGRADE=1
    fi

    if [ "$(hiera -c /etc/puppet/hiera.yaml bootstrap_nodeid)" = "$(facter hostname)" ]; then
        if [ $DO_MYSQL_UPGRADE -eq 1 ]; then

            if [ -d "$MYSQL_BACKUP_DIR" ]; then
                echo_error "Error: $MYSQL_BACKUP_DIR exists already. Likely an upgrade failed previously"
                exit 1
            fi
            mkdir "$MYSQL_BACKUP_DIR"
            if [ $? -ne 0 ]; then
                echo_error "Error: could not create temporary backup directory $MYSQL_BACKUP_DIR"
                exit 1
            fi

            # the /root/.my.cnf is needed because we set the mysql root
            # password from liberty onwards
            backup_flags="--defaults-extra-file=/root/.my.cnf -u root --flush-privileges --all-databases --single-transaction"
            # While not ideal, this step allows us to calculate exactly how much space the dump
            # will need. Our main goal here is avoiding any chance of corruption due to disk space
            # exhaustion
            backup_size=$(mysqldump $backup_flags 2>/dev/null | wc -c)
            database_size=$(du -cb /var/lib/mysql | tail -1 | awk '{ print $1 }')
            free_space=$(df -B1 --output=avail "$MYSQL_BACKUP_DIR" | tail -1)

            # we need at least space for a new mysql database + dump of the existing one,
            # times a small factor for additional safety room
            # note: bash doesn't do floating point math or floats in if statements,
            # so use python to apply the ratio and cast it back to integer
            required_space=$(python -c "from __future__ import print_function; print(\"%d\" % int((($database_size + $backup_size) * $MYSQL_BACKUP_SIZE_RATIO)))")
            if [ $required_space -ge $free_space ]; then
                echo_error "Error: not enough free space in $MYSQL_BACKUP_DIR ($required_space bytes required)"
                exit 1
            fi
        fi
    fi
}

check_python_rpm()
{
    # If for some reason rpm-python are missing we want to error out early enough
    if ! rpm -q rpm-python &> /dev/null; then
        echo_error "ERROR: upgrade cannot start without rpm-python installed"
        exit 1
    fi
}

check_clean_cluster()
{
    if pcs status | grep -q Stopped:; then
        echo_error "ERROR: upgrade cannot start with stopped resources on the cluster. Make sure that all the resources are up and running."
        exit 1
    fi
}

check_galera_root_password()
{
    # BZ: 1357112
    if [ ! -e /root/.my.cnf ]; then
        echo_error "ERROR: upgrade cannot be started, the galera password is missing. The overcloud needs update."
        exit 1
    fi
}
