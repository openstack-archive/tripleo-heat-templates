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

import json
import os
from pathlib import Path
import shutil
import subprocess
import yaml

CONF = json.loads(os.environ['config'])


def _run_command(args, env=None, name=None):
    """Run the command defined by args and return its output

    :param args: List of arguments for the command to be run.
    :param env: Dict defining the environment variables. Pass None to use
        the current environment.
    :param name: User-friendly name for the command being run. A value of
        None will cause args[0] to be used.
    """
    if name is None:
        name = args[0]

    if env is None:
        env = os.environ
    env = env.copy()

    # When running a localized python script, we need to tell it that we're
    # using utf-8 for stdout, otherwise it can't tell because of the pipe.
    env['PYTHONIOENCODING'] = 'utf8'

    try:
        return subprocess.check_output(args,
                                       stderr=subprocess.STDOUT,
                                       env=env).decode('utf-8')
    except subprocess.CalledProcessError as ex:
        print('ERROR: %s failed: %s' % (name, ex.output))
        raise


def create_update_clouds_yaml():
    """create clouds.yaml"""
    clouds_yaml_dir = '/etc/openstack'
    clouds_yaml = os.path.join(clouds_yaml_dir, 'clouds.yaml')
    cloud_name = CONF.get('cloud_name', 'undercloud')
    Path(clouds_yaml_dir).mkdir(parents=True, exist_ok=True)

    usr_clouds_yaml_dir = os.path.join(CONF['home_dir'], '.config/openstack')
    usr_clouds_yaml = os.path.join(usr_clouds_yaml_dir, 'clouds.yaml')
    Path(usr_clouds_yaml_dir).mkdir(parents=True, exist_ok=True)

    data = {}
    if os.path.exists(clouds_yaml):
        with open(clouds_yaml, 'r') as fs:
            data = yaml.safe_load(fs)

    if 'clouds' not in data:
        data['clouds'] = {}

    data['clouds'][cloud_name] = {}
    config = {}
    config['auth_type'] = 'http_basic'
    config['auth'] = {}
    config['auth']['username'] = 'admin'
    config['auth']['password'] = CONF.get('admin_password', 'admin')
    config['baremetal_endpoint_override'] = CONF.get(
        'endpoints', {}).get('baremetal', 'https://192.168.24.2:13385/')
    config['network_endpoint_override'] = CONF.get(
            'endpoints', {}).get('network', 'https://192.168.24.2:13696/')
    config['baremetal_introspection_endpoint_override'] = CONF.get(
            'endpoints', {}).get(
                'baremetal_introspection', 'https://192.168.24.2:13696/')
    config['baremetal_api_version'] = '1'
    config['network_api_version'] = '2'

    data['clouds'][cloud_name] = config

    fdesc = os.open(path=clouds_yaml,
                    flags=(os.O_WRONLY | os.O_CREAT | os.O_TRUNC),
                    mode=0o600)
    with open(fdesc, 'w') as fs:
        fs.write(yaml.dump(data, default_flow_style=False))

    shutil.copyfile(clouds_yaml, usr_clouds_yaml)

    stat_info = os.stat(CONF['home_dir'])
    os.chown(usr_clouds_yaml_dir, stat_info.st_uid, stat_info.st_gid)
    os.chown(usr_clouds_yaml, stat_info.st_uid, stat_info.st_gid)


keystone_enabled = 'true' in _run_command(
    ['hiera', 'keystone_enabled']).lower()
if not keystone_enabled:
    create_update_clouds_yaml()
