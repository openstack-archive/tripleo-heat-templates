# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import ansible_runner


role_paths = [
    'tripleo-ansible/tripleo-ansible/tripleo_ansible/roles'
]

module_paths = [
    'tripleo-ansible/tripleo-ansible/tripleo_ansible/ansible_plugins/modules'
]


def append_path(path, new):
    if path == '':
        return new
    else:
        return path + ':' + new


def test_tht_ansible_syntax(pytestconfig):
    role_path = ''
    mod_path = ''
    tht_root = str(pytestconfig.invocation_params.dir)
    tht_test_path = os.path.join(tht_root, 'tripleo_heat_templates/tests')

    for r in role_paths:
        role_path = append_path(
            role_path, os.path.join(tht_test_path, r))

    for m in module_paths:
        mod_path = append_path(
            mod_path, os.path.join(tht_test_path, m))

    play_path = os.path.join(tht_test_path, 'test_tht_ansible_syntax.yml')

    os.environ["ANSIBLE_ROLES_PATH"] = role_path
    os.environ["ANSIBLE_LIBRARY"] = mod_path

    run = ansible_runner.run(
        playbook=play_path,
        extravars={'tht_root': tht_root}
    )

    try:
        assert run.rc == 0
    finally:
        print("{}: {}".format(run.status, run.rc))
