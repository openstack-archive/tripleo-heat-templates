#!/usr/bin/env python
import os
import yaml


AUTH_URL = os.environ['auth_url']
ADMIN_PASSWORD = os.environ['admin_password']
CLOUD_NAME = os.environ['cloud_name']
HOME_DIR = os.environ['home_dir']
IDENTITY_API_VERSION = os.environ['identity_api_version']
PROJECT_NAME = os.environ['project_name']
PROJECT_DOMAIN_NAME = os.environ['project_domain_name']
REGION_NAME = os.environ['region_name']
USER_NAME = os.environ['user_name']
USER_DOMAIN_NAME = os.environ['user_domain_name']

CONFIG_DIR = os.path.join(HOME_DIR, '.config')
OS_DIR = os.path.join(CONFIG_DIR, 'openstack')
USER_CLOUDS_YAML = os.path.join(OS_DIR, 'clouds.yaml')
GLOBAL_OS_DIR = os.path.join('/etc', 'openstack')
GLOBAL_CLOUDS_YAML = os.path.join(GLOBAL_OS_DIR, 'clouds.yaml')

CLOUD = {CLOUD_NAME: {'auth': {'auth_url': AUTH_URL,
                               'project_name': PROJECT_NAME,
                               'project_domain_name': PROJECT_DOMAIN_NAME,
                               'username': USER_NAME,
                               'user_domain_name': USER_DOMAIN_NAME,
                               'password': ADMIN_PASSWORD},
                      'region_name': REGION_NAME,
                      'identity_api_version': IDENTITY_API_VERSION}
         }


def _create_clouds_yaml(clouds_yaml):
    with open(clouds_yaml, 'w') as f:
        yaml.dump({'clouds': {}}, f, default_flow_style=False)
    os.chmod(clouds_yaml, 0o600)


def _read_clouds_yaml(clouds_yaml):
    with open(clouds_yaml, 'r') as f:
        clouds = yaml.safe_load(f)
        if 'clouds' not in clouds:
            clouds.update({'clouds': {}})

    return clouds


def _write_clouds_yaml(clouds_yaml, clouds):
    with open(clouds_yaml, 'w') as f:
        yaml.dump(clouds, f, default_flow_style=False)


try:
    # Get the uid and gid for the homedir
    user_id = os.stat(HOME_DIR).st_uid
    group_id = os.stat(HOME_DIR).st_gid

    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        os.chown(CONFIG_DIR, user_id, group_id)

    if not os.path.isdir(OS_DIR):
        os.makedirs(OS_DIR)
        os.chown(OS_DIR, user_id, group_id)

    if not os.path.isdir(GLOBAL_OS_DIR):
        os.makedirs(GLOBAL_OS_DIR)

    if not os.path.isfile(USER_CLOUDS_YAML):
        _create_clouds_yaml(USER_CLOUDS_YAML)

    if not os.path.isfile(GLOBAL_CLOUDS_YAML):
        _create_clouds_yaml(GLOBAL_CLOUDS_YAML)

    user_clouds = _read_clouds_yaml(USER_CLOUDS_YAML)
    global_clouds = _read_clouds_yaml(GLOBAL_CLOUDS_YAML)

    user_clouds['clouds'].update(CLOUD)
    global_clouds['clouds'].update(CLOUD)

    _write_clouds_yaml(USER_CLOUDS_YAML, user_clouds)
    _write_clouds_yaml(GLOBAL_CLOUDS_YAML, global_clouds)

    os.chown(USER_CLOUDS_YAML, user_id, group_id)
except Exception:
    print('ERROR: Create clouds.yaml failed.')
    raise
