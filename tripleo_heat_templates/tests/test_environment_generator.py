# Copyright 2015 Red Hat Inc.
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

from tripleo_heat_templates import environment_generator

load_tests = testscenarios.load_tests_apply_scenarios

basic_template = '''
parameters:
  FooParam:
    default: foo
    description: Foo description
    type: string
  BarParam:
    default: 42
    description: Bar description
    type: number
  EndpointMap:
    default: {}
    description: Parameter that should not be included by default
    type: json
resources:
  # None
'''
basic_private_template = '''
parameters:
  FooParam:
    default: foo
    description: Foo description
    type: string
  _BarParam:
    default: 42
    description: Bar description
    type: number
resources:
  # None
'''
mandatory_template = '''
parameters:
  FooParam:
    description: Mandatory param
    type: string
resources:
  # None
'''
index_template = '''
parameters:
  FooParam:
    description: Param with %index% as its default
    type: string
    default: '%index%'
resources:
  # None
'''
multiline_template = '''
parameters:
  FooParam:
    description: |
      Parameter with
      multi-line description
    type: string
    default: ''
resources:
  # None
'''
basic_role_param_template = '''
parameters:
  RoleParam:
    description: Role param description
    type: string
    default: ''
  FooParam:
    description: Foo description
    default: foo
    type: string
resources:
  # None
'''
multiline_role_param_template = '''
parameters:
  RoleParam:
    description: |
      Role Parameter with
      multi-line description
    type: string
    default: ''
  FooParam:
    description: |
      Parameter with
      multi-line description
    type: string
    default: ''
resources:
  # None
'''


class GeneratorTestCase(base.BaseTestCase):
    content_scenarios = [
        ('basic',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Bar description
  # Type: number
  BarParam: 42

  # Foo description
  # Type: string
  FooParam: foo

''',
          }),
        ('basic-one-param',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters:
          - FooParam
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Foo description
  # Type: string
  FooParam: foo

''',
          }),
        ('basic-static-param',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    static:
      - BarParam
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Foo description
  # Type: string
  FooParam: foo

  # ******************************************************
  # Static parameters - these are values that must be
  # included in the environment but should not be changed.
  # ******************************************************
  # Bar description
  # Type: number
  BarParam: 42

  # *********************
  # End static parameters
  # *********************
''',
          }),
        ('basic-static-param-sample',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    static:
      - BarParam
    sample_values:
      BarParam: 1
      FooParam: ''
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Foo description
  # Type: string
  FooParam: ''

  # ******************************************************
  # Static parameters - these are values that must be
  # included in the environment but should not be changed.
  # ******************************************************
  # Bar description
  # Type: number
  BarParam: 1

  # *********************
  # End static parameters
  # *********************
''',
          }),
        ('basic-private',
         {'template': basic_private_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Foo description
  # Type: string
  FooParam: foo

''',
          }),
        ('mandatory',
         {'template': mandatory_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Mandatory param
  # Mandatory. This parameter must be set by the user.
  # Type: string
  FooParam: <None>

''',
          }),
        ('basic-sample',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    sample_values:
      FooParam: baz
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Bar description
  # Type: number
  BarParam: 42

  # Foo description
  # Type: string
  FooParam: baz

''',
          }),
        ('basic-resource-registry',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    resource_registry:
      OS::TripleO::FakeResource: fake-filename.yaml
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Bar description
  # Type: number
  BarParam: 42

  # Foo description
  # Type: string
  FooParam: foo

resource_registry:
  OS::TripleO::FakeResource: fake-filename.yaml
''',
          }),
        ('basic-hidden',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    sample_values:
      EndpointMap: |-2

            foo: bar
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Bar description
  # Type: number
  BarParam: 42

  # Parameter that should not be included by default
  # Type: json
  EndpointMap:
    foo: bar

  # Foo description
  # Type: string
  FooParam: foo

''',
          }),
        ('missing-param',
         {'template': basic_template,
          'exception': RuntimeError,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters:
          - SomethingNonexistent
''',
          'expected_output': None,
          }),
        ('percent-index',
         {'template': index_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Param with %index% as its default
  # Type: string
  FooParam: '%index%'

''',
          }),
        ('nested',
         {'template': multiline_template,
          'exception': None,
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
    children:
      - name: nested
        title: Nested Environment
        description: Nested description
        sample_values:
          FooParam: bar
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Parameter with
  # multi-line description
  # Type: string
  FooParam: ''

''',
          'nested_output': '''# title: Nested Environment
# description: |
#   Nested description
parameter_defaults:
  # Parameter with
  # multi-line description
  # Type: string
  FooParam: bar

''',
          }),
        ('multi-line-desc',
         {'template': multiline_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    files:
      foo.yaml:
        parameters: all
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
parameter_defaults:
  # Parameter with
  # multi-line description
  # Type: string
  FooParam: ''

''',
          }),
        ('basic_role_param',
         {'template': basic_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic_role_param
    title: Basic Role Parameters Environment
    description: Basic description
    files:
      foo.yaml:
        RoleParameters:
          - RoleParam
''',
          'expected_output': '''# title: Basic Role Parameters Environment
# description: |
#   Basic description
parameter_defaults:
  RoleParameters:
    # Role param description
    # Type: string
    RoleParam: ''

''',
          }),
        ('multiline_role_param',
         {'template': multiline_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: multiline_role_param
    title: Multiline Role Parameters Environment
    description: Multiline description
    files:
      foo.yaml:
        RoleParameters:
          - RoleParam
''',
          'expected_output': '''# title: Multiline Role Parameters Environment
# description: |
#   Multiline description
parameter_defaults:
  RoleParameters:
    # Role Parameter with
    # multi-line description
    # Type: string
    RoleParam: ''

''',
          }),
        ('Basic mix params',
         {'template': basic_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic_mix_params
    title: Basic Mix Parameters Environment
    description: Basic description
    files:
      foo.yaml:
        parameters:
          - FooParam
        RoleParameters:
          - RoleParam
''',
          'expected_output': '''# title: Basic Mix Parameters Environment
# description: |
#   Basic description
parameter_defaults:
  # Foo description
  # Type: string
  FooParam: foo

  RoleParameters:
    # Role param description
    # Type: string
    RoleParam: ''

''',
          }),
        ('Multiline mix params',
         {'template': multiline_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: multiline_mix_params
    title: Multiline mix params Environment
    description: Multiline description
    files:
      foo.yaml:
        parameters:
          - FooParam
        RoleParameters:
          - RoleParam
''',
          'expected_output': '''# title: Multiline mix params Environment
# description: |
#   Multiline description
parameter_defaults:
  # Parameter with
  # multi-line description
  # Type: string
  FooParam: ''

  RoleParameters:
    # Role Parameter with
    # multi-line description
    # Type: string
    RoleParam: ''

''',
          }),
        ('Basic role static param',
         {'template': basic_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic_role_static_param
    title: Basic Role Static Prams Environment
    description: Basic Role Static Prams description
    files:
      foo.yaml:
        parameters:
          - FooParam
        RoleParameters:
          - RoleParam
    static:
      - FooParam
      - RoleParam
''',
          'expected_output': '''# title: Basic Role Static Prams Environment
# description: |
#   Basic Role Static Prams description
parameter_defaults:
  # ******************************************************
  # Static parameters - these are values that must be
  # included in the environment but should not be changed.
  # ******************************************************
  # Foo description
  # Type: string
  FooParam: foo

  # *********************
  # End static parameters
  # *********************
  RoleParameters:
    # ******************************************************
    # Static parameters - these are values that must be
    # included in the environment but should not be changed.
    # ******************************************************
    # Role param description
    # Type: string
    RoleParam: ''

    # *********************
    # End static parameters
    # *********************
''',
          }),
        ('Multiline role static param',
         {'template': multiline_role_param_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: multline_role_static_param
    title: Multiline Role Static Prams Environment
    description: Multiline Role Static Prams description
    files:
      foo.yaml:
        parameters:
          - FooParam
        RoleParameters:
          - RoleParam
    static:
      - FooParam
      - RoleParam
''',
          'expected_output': '''# title: Multiline Role Static Prams Environment
# description: |
#   Multiline Role Static Prams description
parameter_defaults:
  # ******************************************************
  # Static parameters - these are values that must be
  # included in the environment but should not be changed.
  # ******************************************************
  # Parameter with
  # multi-line description
  # Type: string
  FooParam: ''

  # *********************
  # End static parameters
  # *********************
  RoleParameters:
    # ******************************************************
    # Static parameters - these are values that must be
    # included in the environment but should not be changed.
    # ******************************************************
    # Role Parameter with
    # multi-line description
    # Type: string
    RoleParam: ''

    # *********************
    # End static parameters
    # *********************
''',
          }),
        ('no-files',
         {'template': basic_template,
          'exception': None,
          'nested_output': '',
          'input_file': '''environments:
  -
    name: basic
    title: Basic Environment
    description: Basic description
    resource_registry:
      foo: bar
''',
          'expected_output': '''# title: Basic Environment
# description: |
#   Basic description
resource_registry:
  foo: bar
''',
          }),
        ]

    @classmethod
    def generate_scenarios(cls):
        cls.scenarios = testscenarios.multiply_scenarios(
            cls.content_scenarios)

    def test_generator(self):
        fake_input = io.StringIO(six.text_type(self.input_file))
        fake_template = io.StringIO(six.text_type(self.template))
        _, fake_output_path = tempfile.mkstemp()
        fake_output = open(fake_output_path, 'w')
        with mock.patch('tripleo_heat_templates.environment_generator.open',
                        create=True) as mock_open:
            mock_se = [fake_input, fake_template, fake_output]
            if 'files:' not in self.input_file:
                # No files were specified so that open call won't happen
                mock_se.remove(fake_template)
            if self.nested_output:
                _, fake_nested_output_path = tempfile.mkstemp()
                fake_nested_output = open(fake_nested_output_path, 'w')
                fake_template2 = io.StringIO(six.text_type(self.template))
                mock_se = [fake_input, fake_template, fake_output,
                           fake_template2, fake_nested_output]
            mock_open.side_effect = mock_se
            if not self.exception:
                environment_generator.generate_environments('ignored.yaml',
                                                            'environments')
            else:
                self.assertRaises(self.exception,
                                  environment_generator.generate_environments,
                                  'ignored.yaml',
                                  'environments')
                return
        expected = environment_generator._FILE_HEADER + self.expected_output
        with open(fake_output_path) as f:
            self.assertEqual(expected, f.read())
        if self.nested_output:
            with open(fake_nested_output_path) as f:
                expected = (environment_generator._FILE_HEADER +
                            self.nested_output)
                self.assertEqual(expected, f.read())

GeneratorTestCase.generate_scenarios()
