#!/usr/bin/env python

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

import errno
import os
import sys
import yaml


_PARAM_FORMAT = u"""  # %(description)s
  %(mandatory)s# Type: %(type)s
  %(name)s:%(default)s
"""
_STATIC_MESSAGE_START = (
    '  # ******************************************************\n'
    '  # Static parameters - these are values that must be\n'
    '  # included in the environment but should not be changed.\n'
    '  # ******************************************************\n'
    )
_STATIC_MESSAGE_END = ('  # *********************\n'
                       '  # End static parameters\n'
                       '  # *********************\n'
                       )
_FILE_HEADER = (
    '# *******************************************************************\n'
    '# This file was created automatically by the sample environment\n'
    '# generator. Developers should use `tox -e genconfig` to update it.\n'
    '# Users are recommended to make changes to a copy of the file instead\n'
    '# of the original, if any customizations are needed.\n'
    '# *******************************************************************\n'
    )
# Certain parameter names can't be changed, but shouldn't be shown because
# they are never intended for direct user input.
_PRIVATE_OVERRIDES = ['server', 'servers', 'NodeIndex', 'DefaultPasswords']
# Hidden params are not included by default when the 'all' option is used,
# but can be explicitly included by referencing them in sample_defaults or
# static.  This allows us to generate sample environments using them when
# necessary, but they won't be improperly included by accident.
_HIDDEN_PARAMS = ['EndpointMap', 'RoleName', 'RoleParameters',
                  'ServiceNetMap', 'ServiceData',
                  ]


def _create_output_dir(target_file):
    try:
        os.makedirs(os.path.dirname(target_file))
    except OSError as e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise


def _generate_environment(input_env, parent_env=None):
    if parent_env is None:
        parent_env = {}
    env = dict(parent_env)
    env.pop('children', None)
    env.update(input_env)
    parameter_defaults = {}
    param_names = []
    sample_values = env.get('sample_values', {})
    static_names = env.get('static', [])
    for template_file, template_data in env['files'].items():
        with open(template_file) as f:
            f_data = yaml.safe_load(f)
            f_params = f_data['parameters']
            parameter_defaults.update(f_params)
            if template_data['parameters'] == 'all':
                new_names = [k for k, v in f_params.items()]
                for hidden in _HIDDEN_PARAMS:
                    if (hidden not in (static_names + list(sample_values)) and
                            hidden in new_names):
                        new_names.remove(hidden)
            else:
                new_names = template_data['parameters']
            missing_params = [name for name in new_names
                              if name not in f_params]
            if missing_params:
                raise RuntimeError('Did not find specified parameter names %s '
                                   'in file %s for environment %s' %
                                   (missing_params, template_file,
                                    env['name']))
            param_names += new_names

    static_defaults = {k: v for k, v in parameter_defaults.items()
                       if k in param_names and
                       k in static_names
                       }
    parameter_defaults = {k: v for k, v in parameter_defaults.items()
                          if k in param_names and
                          k not in _PRIVATE_OVERRIDES and
                          not k.startswith('_') and
                          k not in static_names
                          }

    for k, v in sample_values.items():
        if k in parameter_defaults:
            parameter_defaults[k]['sample'] = v
        if k in static_defaults:
            static_defaults[k]['sample'] = v

    def write_sample_entry(f, name, value):
        default = value.get('default')
        mandatory = ''
        if default is None:
            mandatory = ('# Mandatory. This parameter must be set by the '
                         'user.\n  ')
            default = '<None>'
        if value.get('sample') is not None:
            default = value['sample']
        # We ultimately cast this to str for output anyway
        default = str(default)
        if default == '':
            default = "''"
        # If the default value is something like %index%, yaml won't
        # parse the output correctly unless we wrap it in quotes.
        # However, not all default values can be wrapped so we need to
        # do it conditionally.
        if default.startswith('%'):
            default = "'%s'" % default
        if not default.startswith('\n'):
            default = ' ' + default

        values = {'name': name,
                  'type': value['type'],
                  'description':
                      value.get('description', '').rstrip().replace('\n',
                                                                    '\n  # '),
                  'default': default,
                  'mandatory': mandatory,
                  }
        f.write(_PARAM_FORMAT % values + '\n')

    target_file = os.path.join('environments', env['name'] + '.yaml')
    _create_output_dir(target_file)
    with open(target_file, 'w') as env_file:
        env_file.write(_FILE_HEADER)
        # TODO(bnemec): Once Heat allows the title and description to live in
        # the environment itself, uncomment these entries and make them
        # top-level keys in the YAML.
        env_title = env.get('title', '')
        env_file.write(u'# title: %s\n' % env_title)
        env_desc = env.get('description', '')
        env_file.write(u'# description: |\n')
        for line in env_desc.splitlines():
            env_file.write(u'#   %s\n' % line)

        if parameter_defaults or static_defaults:
            env_file.write(u'parameter_defaults:\n')
        for name, value in sorted(parameter_defaults.items()):
            write_sample_entry(env_file, name, value)
        if static_defaults:
            env_file.write(_STATIC_MESSAGE_START)
        for name, value in sorted(static_defaults.items()):
            write_sample_entry(env_file, name, value)
        if static_defaults:
            env_file.write(_STATIC_MESSAGE_END)

        if env.get('resource_registry'):
            env_file.write(u'resource_registry:\n')
        for res, value in sorted(env.get('resource_registry', {}).items()):
            env_file.write(u'  %s: %s\n' % (res, value))
        print('Wrote sample environment "%s"' % target_file)

    for e in env.get('children', []):
        _generate_environment(e, env)


def generate_environments(config_path):
    if os.path.isdir(config_path):
        config_files = os.listdir(config_path)
        config_files = [os.path.join(config_path, i) for i in config_files
                        if os.path.splitext(i)[1] == '.yaml']
    else:
        config_files = [config_path]
    for config_file in config_files:
        print('Reading environment definitions from %s' % config_file)
        with open(config_file) as f:
            config = yaml.safe_load(f)
        for env in config['environments']:
            _generate_environment(env)


def usage(exit_code=1):
    print('Usage: %s [<filename.yaml> | <directory>]' % sys.argv[0])
    sys.exit(exit_code)


def main():
    try:
        config_path = sys.argv[1]
    except IndexError:
        usage()
    generate_environments(config_path)


if __name__ == '__main__':
    main()
