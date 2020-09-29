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
import sys
import yaml


def parse_opts(argv):
    parser = argparse.ArgumentParser(
            description='Convert to new NIC config templates with '
                        'OS::Heat::Value resources.')
    parser.add_argument('-t', '--template', metavar='TEMPLATE_FILE',
                        help=("Existing NIC config template to conver."),
                        required=True)
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


class TemplateDumper(yaml.SafeDumper):
    def represent_ordered_dict(self, data):
        return self.represent_dict(data.items())

    def description_presenter(self, data):
        if not len(data) > 80:
            return self.represent_scalar('tag:yaml.org,2002:str', data)
        return self.represent_scalar('tag:yaml.org,2002:str', data, style='>')


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


def write_template(template, filename=None):
    with open(filename, 'w') as f:
        yaml.dump(template, f, TemplateDumper, width=120,
                  default_flow_style=False)


def validate_template(template):
    if not os.path.exists(template):
        raise RuntimeError('Template not provided.')
    if not os.path.isfile(template):
        raise RuntimeError('Template %s is not a file.')
    pass


def backup_template(template):
    extension = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    backup_filename = os.path.realpath(template) + '.' + extension
    if os.path.exists(backup_filename):
        raise RuntimeError('Backupe file: %s already exists. Aborting!'
                           % backup_filename)
    shutil.copyfile(template, backup_filename)
    print('The original template was saved as: %s' % backup_filename)


def needs_conversion():
    with open(OPTS.template, 'r') as f:
        template = yaml.load(f.read(), Loader=TemplateLoader)
    net_config_res = template['resources'].get('OsNetConfigImpl')
    if (net_config_res and net_config_res[
            'type'] == 'OS::Heat::SoftwareConfig'):
        backup_template(OPTS.template)
        if not OPTS.discard_comments:
            # Convert comments '# ...' into 'comments<num>: ...'
            # is not lost when loading the data.
            to_commented_yaml(OPTS.template)
        return True
    return False


def convert_to_heat_value_resource():
    if needs_conversion():
        with open(OPTS.template, 'r') as f:
            template = yaml.load(f.read(), Loader=TemplateLoader)
        net_config_res = template['resources']['OsNetConfigImpl']
        net_config_res_props = net_config_res['properties']
        # set the type to OS::Heat::Value
        net_config_res['type'] = 'OS::Heat::Value'
        del net_config_res_props['group']
        old_config = net_config_res_props['config']
        new_config = old_config['str_replace']['params']['$network_config']
        net_config_res_props['config'] = new_config
        outputs = template['outputs']
        del outputs['OS::stack_id']
        outputs['config'] = {}
        outputs['config']['value'] = 'get_attr[OsNetConfigImpl, value]'
        write_template(template, filename=OPTS.template)
        if not OPTS.discard_comments:
            # Convert previously converted comments, 'comments<num>: ...'
            # YAML back to normal #commented YAML
            to_normal_yaml(OPTS.template)
        print('The update template was saved as: %s' % OPTS.template)
    else:
        print('Template does not need conversion: %s' % OPTS.template)


OPTS = parse_opts(sys.argv)
convert_to_heat_value_resource()
