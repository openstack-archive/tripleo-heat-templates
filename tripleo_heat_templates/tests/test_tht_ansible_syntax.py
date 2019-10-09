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


def test_tht_ansible_syntax(pytestconfig):

    tht_root = str(pytestconfig.invocation_params.dir)
    role_path = os.path.join(tht_root,
                             "tripleo_heat_templates/tests/roles/tripleo-ansible/tripleo-ansible/tripleo_ansible/roles")
    play_path = os.path.join(tht_root,
                             "tripleo_heat_templates/tests/test_tht_ansible_syntax.yml")

    os.environ["ANSIBLE_ROLES_PATH"] = role_path

    run = ansible_runner.run(
        playbook=play_path,
        extravars={'tht_root': tht_root}
    )

    try:
        assert run.rc == 0
    finally:
        print("{}: {}".format(run.status, run.rc))
