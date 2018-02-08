# Copyright 2018 Red Hat Inc.
#
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

import io
import tempfile

import mock
from oslotest import base
import six
import testscenarios
import yaml
import yaql


class YAQLTestCase(base.BaseTestCase):

    def get_snippet(self, template, path):
        with open(template) as f:
            template = f.read()
            data = yaml.safe_load(template)
            for i in path.split('.'):
                data = data[i]
            return data['yaql']['expression']

