#!/usr/bin/env python
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

import argparse
import collections
import datetime
import os
import re
import shutil
import six
import subprocess
import sys
import yaml

from tempfile import mkdtemp

DEFAULT_THT_DIR = '/usr/share/openstack-tripleo-heat-templates'
NIC_CONFIG_REFERENCE = 'single-nic-vlans'


def parse_opts(argv):
    parser = argparse.ArgumentParser(
            description='Merge new NIC config template parameters into '
                        'existing NIC config template.')
    parser.add_argument('-r', '--roles-data', metavar='ROLES_DATA',
                        help="Relative path to the roles_data.yaml file.",
                        default=('%s/roles_data.yaml') % DEFAULT_THT_DIR)
    parser.add_argument('-n', '--network-data', metavar='NETWORK_DATA',
                        help="Relative path to the network_data.yaml file.",
                        default=('%s/network_data.yaml') % DEFAULT_THT_DIR)
    parser.add_argument('--role-name', metavar='ROLE-NAME',
                        help="Name of the role the NIC config is used for.",
                        required=True)
    parser.add_argument('-t', '--template', metavar='TEMPLATE_FILE',
                        help=("Existing NIC config template to merge "
                              "parameter too."),
                        required=True)
    parser.add_argument('--tht-dir', metavar='THT_DIR',
                        help=("Path to tripleo-heat-templates (THT) "
                              "directory"),
                        default=DEFAULT_THT_DIR)
    parser.add_argument('--discard-comments', metavar='DISCARD_COMMENTS',
                        help="Discard comments from the template. (The "
                             "scripts functions to keep YAML file comments in "
                             "place, does not work in all scenarios.)",
                        default=False)

    opts = parser.parse_args(argv[1:])

    return opts


def to_commented_yaml(filename):
    """Convert comments into 'comments<num>: ...' YAML"""

    out_str = ''
    last_non_comment_spaces = ''
    with open(filename, 'r') as f:
        comment_count = 0
        for line in f:
            # skip blank line
            if line.isspace():
                continue
            char_count = 0
            spaces = ''
            for char in line:
                char_count += 1
                if char == ' ':
                    spaces += ' '
                    next
                elif char == '#':
                    comment_count += 1
                    comment = line[char_count:-1]
                    last_non_comment_spaces = spaces
                    out_str += "%scomment%i_%i: '%s'\n" % (
                        last_non_comment_spaces, comment_count, len(spaces),
                        comment)
                    break
                else:
                    last_non_comment_spaces = spaces
                    out_str += line

                    # inline comments check
                    m = re.match(".*:.*#(.*)", line)
                    if m:
                        comment_count += 1
                        out_str += "%s  inline_comment%i: '%s'\n" % (
                            last_non_comment_spaces, comment_count, m.group(1))
                    break

    with open(filename, 'w') as f:
        f.write(out_str)

    return out_str


def to_normal_yaml(filename):
    """Convert back to normal #commented YAML"""

    with open(filename, 'r') as f:
        data = f.read()

    out_str = ''
    next_line_break = False
    for line in data.split('\n'):
        # get_input not supported by run-os-net-config.sh script
        line = line.replace('get_input: ', '')
        # Normal comments
        m = re.match(" +comment[0-9]+_([0-9]+): '(.*)'.*", line)
        # Inline comments
        i = re.match(" +inline_comment[0-9]+: '(.*)'.*", line)
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


# FIXME: Some of this duplicates code from build_endpoint_map.py, we should
# refactor to share the common code
class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())

    def description_presenter(self, data):
        if not len(data) > 80:
            return self.represent_scalar('tag:yaml.org,2002:str', data)
        return self.represent_scalar('tag:yaml.org,2002:str', data, style='>')


# FIXME: This duplicates code from tools/yaml-nic-config-2-script.py, we should
# refactor to share the common code
# We load mappings into OrderedDict to preserve their order
class TemplateLoader(yaml.SafeLoader):
    def construct_mapping(self, node):
        self.flatten_mapping(node)
        return collections.OrderedDict(self.construct_pairs(node))


TemplateDumper.add_representer(six.text_type,
                               TemplateDumper.description_presenter)
TemplateDumper.add_representer(six.binary_type,
                               TemplateDumper.description_presenter)

TemplateDumper.add_representer(collections.OrderedDict,
                               TemplateDumper.represent_ordered_dict)
TemplateLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                               TemplateLoader.construct_mapping)


# FIXME: This duplicates code from tools/yaml-nic-config-2-script.py, we should
# refactor to share the common code
def write_template(template, filename=None):
    with open(filename, 'w') as f:
        yaml.dump(template, f, TemplateDumper, width=120,
                  default_flow_style=False)


def process_templates_and_get_reference_parameters():
    temp_dir = mkdtemp(dir='/tmp')
    executable = OPTS.tht_dir + '/tools/process-templates.py'
    cmd = [executable,
           '--roles-data ' + OPTS.roles_data,
           '--base_path ' + OPTS.tht_dir,
           '--network-data ' + OPTS.network_data,
           '--output-dir ' + temp_dir]
    child = subprocess.Popen(' '.join(cmd), shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
    out, err = child.communicate()
    if not child.returncode == 0:
        raise RuntimeError('Error processing templates: %s' % err)

    # If deprecated_nic_config_names is set for role the deprecated name must
    # be used when loading the reference file.
    with open(OPTS.roles_data) as roles_data_file:
        roles_data = yaml.safe_load(roles_data_file)
    try:
        nic_config_name = next((x.get('deprecated_nic_config_name',
                                      OPTS.role_name.lower() + '.yaml')
                                for x in roles_data
                                if x['name'] == OPTS.role_name))
    except StopIteration:
        raise RuntimeError(
            'The role: {role_name} is not defined in roles '
            'data file: {roles_data_file}'.format(
                role_name=OPTS.role_name, roles_data_file=OPTS.roles_data))

    refernce_file = '/'.join([temp_dir, 'network/config', NIC_CONFIG_REFERENCE,
                              nic_config_name])
    with open(refernce_file) as reference:
        reference_template = yaml.safe_load(reference)
    reference_params = reference_template['parameters']
    shutil.rmtree(temp_dir)

    return reference_params


def validate_template():
    if not os.path.exists(OPTS.template):
        raise RuntimeError('Template not provided.')
    if not os.path.isfile(OPTS.template):
        raise RuntimeError('Template %s is not a file.')
    pass


def backup_template():
    extension = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    backup_filename = os.path.realpath(OPTS.template) + '.' + extension
    if os.path.exists(backup_filename):
        raise RuntimeError('Backupe file: %s already exists. Aborting!'
                           % backup_filename)
    shutil.copyfile(OPTS.template, backup_filename)
    print('The original template was saved as: %s' % backup_filename)


def merge_from_processed(reference_params):
    with open(OPTS.template, 'r') as f:
        template = yaml.load(f.read(), Loader=TemplateLoader)

    for param in reference_params:
        if param not in template['parameters']:
            template['parameters'][param] = reference_params[param]

    write_template(template, filename=OPTS.template)
    print('The update template was saved as: %s' % OPTS.template)


OPTS = parse_opts(sys.argv)
validate_template()
backup_template()
if not OPTS.discard_comments:
    # Convert comments '# ...' into 'comments<num>: ...' YAML so that the info
    # is not lost when loading the data.
    to_commented_yaml(OPTS.template)
reference_params = process_templates_and_get_reference_parameters()
merge_from_processed(reference_params)
if not OPTS.discard_comments:
    # Convert previously converted comments, 'comments<num>: ...' YAML back to
    # normal #commented YAML
    to_normal_yaml(OPTS.template)
