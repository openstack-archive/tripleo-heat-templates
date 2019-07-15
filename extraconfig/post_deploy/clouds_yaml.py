#!/usr/bin/env python
# Copyright 2018, 2019 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

from tripleo_common.utils import clouds_yaml
from tripleoclient import constants


def _get_cloud_config():
    cloud_config = {
        os.environ["cloud_name"]: {
            "auth": {
                "auth_url": os.environ["auth_url"],
                "project_name": os.environ["project_name"],
                "project_domain_name": os.environ["project_domain_name"],
                "username": os.environ["user_name"],
                "user_domain_name": os.environ["user_domain_name"],
                "password": os.environ["admin_password"],
            },
            "region_name": os.environ["region_name"],
            "identity_api_version": os.environ["identity_api_version"],
        }
    }
    return cloud_config


if __name__ == "__main__":
    cloud = _get_cloud_config()
    home_dir = os.path.join(os.environ["home_dir"])
    user_id = os.stat(home_dir).st_uid
    group_id = os.stat(home_dir).st_gid
    clouds_yaml.create_clouds_yaml(
        cloud=cloud,
        cloud_yaml_dir=os.path.join(home_dir, constants.CLOUDS_YAML_DIR),
        user_id=user_id,
        group_id=group_id,
    )

    # Generate clouds.yaml globally
    clouds_yaml.create_clouds_yaml(cloud=cloud)
