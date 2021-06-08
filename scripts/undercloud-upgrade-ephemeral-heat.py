#!/usr/libexec/platform-python
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

"""Migrate an undercloud's stack data to use ephemeral Heat. Queries for
existing stacks and exports necessary data from the stack to the default
consistent working directory before backing up and dropping the heat database.
"""

import argparse
import logging
import os
import subprocess
import tarfile
import time
import yaml

from heatclient.client import Client
import keystoneauth1
import openstack
from tripleo_common.utils import plan as plan_utils


LOG = logging.getLogger('undercloud')


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upgrade an undercloud for ephemeral Heat.")

    parser.add_argument(
        '--cloud', '-c',
        default='undercloud',
        help='The name of the cloud used for the OpenStack connection.')
    parser.add_argument(
        '--stack', '-s',
        action='append',
        help='The stack(s) to migrate to using ephemeral Heat. Can be '
             'specified multiple times. If not specified, all stacks '
             'will be migrated')
    parser.add_argument(
        '--working-dir', '-w',
        help='Directory to use for saving stack state. '
             'Defaults to ~/overcloud-deploy/<stack>')

    return parser.parse_args()


def database_exists():
    """Check if the heat database exists.

    :return: True if the heat database exists, otherwise False
    :rtype: bool
    """
    output = subprocess.check_output([
        'sudo', 'podman', 'exec', '-u', 'root', 'mysql',
        'mysql', '-e', 'show databases like "heat"'
    ])
    return 'heat' in str(output)


def backup_db(backup_dir):
    """Backup the heat database to the specified directory

    :param backup_dir: The directory to store the backup
    :type backup_dir: str
    :return: Database tarfile backup path
    :rtype: str
    """
    heat_dir = os.path.join(backup_dir, 'heat-launcher')
    if not os.path.isdir(heat_dir):
        os.makedirs(heat_dir)
    db_path = os.path.join(heat_dir, 'heat-db.sql')
    LOG.info("Backing up heat database to {}".format(db_path))
    with open(db_path, 'w') as out:
        subprocess.run([
            'sudo', 'podman', 'exec', '-u', 'root',
            'mysql', 'mysqldump', 'heat'], stdout=out,
            check=True)
    os.chmod(db_path, 0o600)

    tf_name = '{}-{}.tar.bzip2'.format(db_path, time.time())
    tf = tarfile.open(tf_name, 'w:bz2')
    tf.add(db_path, os.path.basename(db_path))
    tf.close()
    LOG.info("Created tarfile {}".format(tf_name))

    return tf_name


def _decode(encoded):
    """Decode a string into utf-8

    :param encoded: Encoded string
    :type encoded: string
    :return: Decoded string
    :rtype: string
    """
    if not encoded:
        return ""
    decoded = encoded.decode('utf-8')
    if decoded.endswith('\n'):
        decoded = decoded[:-1]
    return decoded


def _get_ctlplane_vip():
    """Get the configured ctlplane VIP

    :return: ctlplane VIP
    :rtype: string
    """
    return _decode(subprocess.check_output(
        ['sudo', 'hiera', 'controller_virtual_ip']))


def _get_ctlplane_ip():
    """Get the configured ctlplane IP

    :return: ctlplane IP
    :rtype: string
    """
    return _decode(subprocess.check_output(
        ['sudo', 'hiera', 'ctlplane']))


def drop_db():
    """Drop the heat database and heat users

    :return: None
    :rtype: None
    """
    LOG.info("Dropping Heat database")
    subprocess.check_call([
        'sudo', 'podman', 'exec', '-u', 'root',
        'mysql', 'mysql', 'heat', '-e',
        'drop database heat'])
    LOG.info("Dropping Heat users")
    subprocess.check_call([
        'sudo', 'podman', 'exec', '-u', 'root',
        'mysql', 'mysql', '-e',
        'drop user \'heat\'@\'{}\''.format(_get_ctlplane_ip())])
    subprocess.check_call([
        'sudo', 'podman', 'exec', '-u', 'root',
        'mysql', 'mysql', '-e',
        'drop user \'heat\'@\'{}\''.format(_get_ctlplane_vip())])
    subprocess.check_call([
        'sudo', 'podman', 'exec', '-u', 'root',
        'mysql', 'mysql', '-e',
        'drop user \'heat\'@\'%\''])


def export_passwords(heat, stack, stack_dir):
    """Export passwords from an existing stack and write them in Heat
    environment file format to the specified directory.

    :param cloud: Heat client
    :type cloud: heatclient.client.Client
    :param stack: Stack name to query for passwords
    :type stack: str
    :param stack_dir: Directory to save the generated Heat environment
        containing the password values.
    :type stack_dir: str
    :return: None
    :rtype: None
    """
    passwords_path = os.path.join(
        stack_dir, "tripleo-{}-passwords.yaml".format(stack))
    LOG.info("Exporting passwords for stack %s to %s"
             % (stack, passwords_path))
    passwords = plan_utils.generate_passwords(heat=heat, container=stack)
    password_params = dict(parameter_defaults=passwords)
    with open(passwords_path, 'w') as f:
        f.write(yaml.safe_dump(password_params))
    os.chmod(passwords_path, 0o600)


def main():
    logging.basicConfig()
    LOG.setLevel(logging.INFO)
    args = parse_args()

    sudo_user = os.environ.get('SUDO_USER')

    if not args.working_dir:
        if sudo_user:
            user_home = '~{}'.format(sudo_user)
        else:
            user_home = '~'

        working_dir = os.path.join(
            os.path.expanduser(user_home),
            'overcloud-deploy')
    else:
        working_dir = args.working_dir
    if not os.path.isdir(working_dir):
        os.makedirs(working_dir)

    try:
        conn = openstack.connection.from_config(cloud=args.cloud)
        heat = conn.orchestration
        _heatclient = Client('1', endpoint=conn.endpoint_for('orchestration'),
                             token=conn.auth_token)
    except keystoneauth1.exceptions.catalog.EndpointNotFound:
        LOG.warning("No Heat endpoint found, won't migrate any "
                    "existing stack data.")
        return

    try:
        stacks = args.stack or [s.name for s in heat.stacks()]
    except openstack.exceptions.HttpException:
        LOG.warning("No connection to Heat available, won't migrate any "
                    "existing stack data.")
        stacks = []

    if database_exists():
        backup_dir = os.path.join(
            working_dir,
            'undercloud-upgrade-ephemeral-heat')
        db_tar_path = backup_db(backup_dir)
    else:
        LOG.warning("No database found to backup.")
        db_tar_path = None

    for stack in stacks:
        stack_dir = os.path.join(working_dir, stack)
        if not os.path.exists(stack_dir):
            os.makedirs(stack_dir)
        if db_tar_path:
            # Symlink to the existing db backup
            os.symlink(db_tar_path,
                os.path.join(stack_dir, os.path.basename(db_tar_path)))
        export_passwords(_heatclient, stack, stack_dir)

    if database_exists():
        drop_db()

    # Chown all files to original user if running under sudo
    if sudo_user:
        subprocess.run([
            'chown', '-R', '{}:{}'.format(sudo_user, sudo_user),
            working_dir],
            check=True)


if __name__ == '__main__':
    main()
