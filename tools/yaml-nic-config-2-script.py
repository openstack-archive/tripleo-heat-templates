#!/usr/bin/env python
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import argparse
import collections
import copy
import datetime
import os
import shutil
import sys
import traceback
import yaml
import six
import re

def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Convert an old style NIC config file into the new format using '
                    'run-os-net-config.sh')
    parser.add_argument('--script-dir', metavar='<script directory>',
                        help="Relative path to run-os-net-config.sh",
                        default="network/scripts/run-os-net-config.sh")
    parser.add_argument('files', nargs="+", metavar='<file>',
                        help='List of one or more NIC config files to convert')
    parser.add_argument('--yes',
                        action='store_true',
                        help=("Use --yes to skip the confirmation "
                               "to overwrite the original config file "),
                        )
    opts = parser.parse_args(argv[1:])

    return opts


#convert comments into 'comments<num>: ...' YAML
def to_commented_yaml(filename):
    out_str = ''
    last_non_comment_spaces = ''
    with open(filename, 'r') as f:
        comment_count = 0
        for line in f:
            # skip blank line
            if line.isspace():
                continue;
            char_count = 0
            spaces = ''
            for char in line:
                char_count += 1
                if char == ' ':
                    spaces+=' '
                    next;
                elif char == '#':
                    comment_count += 1
                    comment = line[char_count:-1]
                    out_str += "%scomment%i_%i: '%s'\n" % (last_non_comment_spaces, comment_count, len(spaces), comment)
                    break;
                else:
                    last_non_comment_spaces = spaces
                    out_str += line

                    #inline comments check
                    m = re.match(".*:.*#(.*)", line)
                    if m:
                        comment_count += 1
                        out_str += "%s  inline_comment%i: '%s'\n" % (last_non_comment_spaces, comment_count, m.group(1))
                    break;

    with open(filename, 'w') as f:
        f.write(out_str)

    return out_str

#convert back to normal #commented YAML
def to_normal_yaml(filename):

    with open(filename, 'r') as f:
        data = f.read()

    out_str = ''
    next_line_break = False
    for line in data.split('\n'):
        # get_input not supported by run-os-net-config.sh script
        line = line.replace('get_input: ', '')
        m = re.match(" +comment[0-9]+_([0-9]+): '(.*)'.*", line) #normal comments
        i = re.match(" +inline_comment[0-9]+: '(.*)'.*", line) #inline comments
        if m:
            if next_line_break:
                out_str += '\n'
                next_line_break = False
            for x in range(0, int(m.group(1))):
                out_str += " "
            out_str += "#%s\n" % m.group(2)
        elif i:
            out_str += " #%s\n" % i.group(1)
            next_line_break = False
        else:
            if next_line_break:
                out_str += '\n'
            out_str += line
            next_line_break = True

    if next_line_break:
        out_str += '\n'

    with open(filename, 'w') as f:
        f.write(out_str)

    return out_str


class description(six.text_type):
    pass

# FIXME: Some of this duplicates code from build_endpoint_map.py, we should
# refactor to share the common code
class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())

    def description_presenter(self, data):
        if '\n' in data:
            style = '>'
        else:
            style = ''
        return self.represent_scalar(
            yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, data, style=style)


# We load mappings into OrderedDict to preserve their order
class TemplateLoader(yaml.SafeLoader):
    def construct_mapping(self, node):
        self.flatten_mapping(node)
        return collections.OrderedDict(self.construct_pairs(node))


TemplateDumper.add_representer(description,
                               TemplateDumper.description_presenter)

TemplateDumper.add_representer(collections.OrderedDict,
                               TemplateDumper.represent_ordered_dict)


TemplateLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                               TemplateLoader.construct_mapping)

def write_template(template, filename=None):
    with open(filename, 'w') as f:
        yaml.dump(template, f, TemplateDumper, width=120, default_flow_style=False)

def convert(filename, script_path):
    print('Converting %s' % filename)
    try:
        tpl = yaml.load(open(filename).read(), Loader=TemplateLoader)
    except Exception:
        print(traceback.format_exc())
        return 0

    for r in (tpl.get('resources', {})).items():
        if (r[1].get('type') == 'OS::Heat::StructuredConfig' and
            r[1].get('properties', {}).get('group') == 'os-apply-config' and
            r[1].get('properties', {}).get('config', {}).get('os_net_config')):
            #print("match %s" % r[0])
            new_r = collections.OrderedDict()
            new_r['type'] = 'OS::Heat::SoftwareConfig'
            new_r['properties'] = collections.OrderedDict()
            new_r['properties']['group'] = 'script'
            old_net_config = r[1].get(
                'properties', {}).get('config', {}).get('os_net_config')
            new_config = {'str_replace': collections.OrderedDict()}
            new_config['str_replace']['template'] = {'get_file': script_path}
            new_config['str_replace']['params'] = {'$network_config': old_net_config}
            new_r['properties']['config'] = new_config
            tpl['resources'][r[0]] = new_r
        else:
            print("No match %s" % r[0])
            return 0

    # Preserve typical HOT template key ordering
    od_result = collections.OrderedDict()
    # Need to bump the HOT version so str_replace supports serializing to json
    od_result['heat_template_version'] = "rocky"
    if tpl.get('description'):
        od_result['description'] = description(tpl['description'])
    od_result['parameters'] = tpl['parameters']
    od_result['resources'] = tpl['resources']
    od_result['outputs'] = tpl['outputs']
    #print('Result:')
    #print('%s' % yaml.dump(od_result, Dumper=TemplateDumper, width=120, default_flow_style=False))
    #print('---')

    write_template(od_result, filename)

    return 1

def check_old_style(filename):

    with open(filename, 'r') as f:
        tpl = yaml.load(open(filename).read())

        if isinstance(tpl.get('resources', {}), dict):
            for r in (tpl.get('resources', {})).items():
                if (r[1].get('type') == 'OS::Heat::StructuredConfig' and
                    r[1].get('properties', {}).get('group') == 'os-apply-config' and
                    r[1].get('properties', {}).get('config', {}).get('os_net_config')):
                    return True

    return False

opts = parse_opts(sys.argv)
exit_val = 0
num_converted = 0

for base_path in opts.files:
    if os.path.isfile(base_path) and base_path.endswith('.yaml'):

        if check_old_style(base_path):

            # Check for script in the user entered (or default) location or in
            # path relative to NIC config files
            script_paths = [opts.script_dir]
            script_paths.append('../../scripts/run-os-net-config.sh')
            script_paths.append('../network/scripts/run-os-net-config.sh')
            script_paths.append(
'/usr/share/openstack-tripleo-heat-templates/network/scripts/run-os-net-config.sh')

            script_path = None
            for p in script_paths:
                if os.path.isfile(os.path.join(os.path.dirname(base_path), p)):
                    script_path = p
                    break
            if script_path is None:
                print("Error couldn't find run-os-net-config.sh relative to filename")
                sys.exit(1)

            print("Using script at %s" % script_path)

            extension = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            backup_filename = os.path.realpath(base_path) + '.' + extension

            print('The yaml file will be overwritten and the original saved as %s'
                  % backup_filename)
            if not (opts.yes or raw_input("Overwrite %s? [y/n] " % base_path).lower() == 'y'):
                print("Skipping file %s" % base_path)
                continue

            if os.path.exists(backup_filename):
                print("Backup file already exists, skipping file %s" % base_path)
                continue

            shutil.copyfile(base_path, backup_filename)

            to_commented_yaml(base_path)
            num_converted += convert(base_path, script_path)
            to_normal_yaml(base_path)
        else:
            print('File %s is not using old style NIC configuration' % base_path)

    else:
        print('Unexpected argument %s' % base_path)

if num_converted == 0:
  exit_val = 1
sys.exit(exit_val)
