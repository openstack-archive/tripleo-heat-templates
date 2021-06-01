#!/usr/bin/env python3
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
import jinja2
import os
import shutil
import six
import sys
import yaml

__tht_root_dir = os.path.dirname(os.path.dirname(__file__))


def _shutil_copy_if_not_same(src, dst):
    """Copy with shutil ignoring the same file errors."""
    if hasattr(shutil, 'SameFileError'):
        try:
            shutil.copy(src, dst)
        except shutil.SameFileError:
            pass
    else:
        try:
            shutil.copy(src, dst)
        except Exception as ex:
            if 'are the same file' in six.text_type(ex):
                pass
            else:
                raise


def parse_opts(argv):
    parser = argparse.ArgumentParser(
        description='Configure host network interfaces using a JSON'
        ' config file format.')
    parser.add_argument('-p', '--base_path', metavar='BASE_PATH',
                        help="""base path of templates to process.""",
                        default='.')
    parser.add_argument('-r', '--roles-data', metavar='ROLES_DATA',
                        help="""relative path to the roles_data.yaml file.""",
                        default='roles_data.yaml')
    parser.add_argument('-n', '--network-data', metavar='NETWORK_DATA',
                        help=("""relative path to the network_data.yaml """
                              """file."""),
                        default='network_data.yaml')
    parser.add_argument('--safe',
                        action='store_true',
                        help="""Enable safe mode (do not overwrite files).""",
                        default=False)
    parser.add_argument('-o', '--output-dir', metavar='OUTPUT_DIR',
                        help="""Output dir for all the templates""",
                        default='')
    parser.add_argument('-c', '--clean',
                        action='store_true',
                        help=("""clean the templates dir by deleting """
                              """generated templates"""))
    parser.add_argument('-d', '--dry-run',
                        action='store_true',
                        help=("""only output file names normally generated """
                              """from j2 templates"""))
    opts = parser.parse_args(argv[1:])

    return opts


def _j2_render_to_file(j2_template, j2_data, outfile_name=None,
                       overwrite=True, dry_run=False):
    yaml_f = outfile_name or j2_template.replace('.j2.yaml', '.yaml')
    if dry_run:
        amend = 'dry run processing'
    else:
        amend = 'rendering'
    print('%s j2 template to file: %s' % (amend, outfile_name))

    if not overwrite and os.path.exists(outfile_name):
        print('ERROR: path already exists for file: %s' % outfile_name)
        sys.exit(1)

    # Search for templates relative to the current template path first
    template_base = os.path.dirname(yaml_f)
    j2_loader = \
        jinja2.loaders.FileSystemLoader([template_base, __tht_root_dir])

    try:
        # Render the j2 template
        template = jinja2.Environment(loader=j2_loader).from_string(
            j2_template)
        r_template = template.render(**j2_data)
    except jinja2.exceptions.TemplateError as ex:
        error_msg = ("Error rendering template %s : %s"
                     % (yaml_f, six.text_type(ex)))
        print(error_msg)
        raise Exception(error_msg)
    if not dry_run:
        with open(outfile_name, 'w') as out_f:
            out_f.write(r_template)


def process_templates(template_path, role_data_path, output_dir,
                      network_data_path, overwrite, dry_run):

    with open(role_data_path) as role_data_file:
        role_data = yaml.safe_load(role_data_file)

    with open(network_data_path) as network_data_file:
        network_data = yaml.safe_load(network_data_file)
        if network_data is None:
            network_data = []

    # Set internal network index key for each network, network resources
    # are created with a tag tripleo_net_idx
    for idx, net in enumerate(network_data):
        network_data[idx].update({'idx': idx})

    j2_excludes = {}
    j2_excludes_path = os.path.join(template_path, 'j2_excludes.yaml')
    if os.path.exists(j2_excludes_path):
        with open(j2_excludes_path) as role_data_file:
            j2_excludes = yaml.safe_load(role_data_file)

    if output_dir and not os.path.isdir(output_dir):
        if os.path.exists(output_dir):
            raise RuntimeError('Output dir %s is not a directory' % output_dir)
        os.mkdir(output_dir)

    role_names = [r.get('name') for r in role_data]
    r_map = {}
    for r in role_data:
        r_map[r.get('name')] = r

    n_map = {}
    for n in network_data:
        if (n.get('enabled') is not False):
            n_map[n.get('name')] = n
            if not n.get('name_lower'):
                n_map[n.get('name')]['name_lower'] = n.get('name').lower()
        else:
            print("skipping %s network: network is disabled" % n.get('name'))

    excl_templates = ['%s/%s' % (template_path, e)
                      for e in j2_excludes.get('name', [])]

    if os.path.isdir(template_path):
        for subdir, dirs, files in os.walk(template_path):

            # NOTE(flaper87): Ignore hidden dirs as we don't
            # generate templates for those.
            # Note the slice assignment for `dirs` is necessary
            # because we need to modify the *elements* in the
            # dirs list rather than the reference to the list.
            # This way we'll make sure os.walk will iterate over
            # the shrunk list. os.walk doesn't have an API for
            # filtering dirs at this point.
            dirs[:] = [d for d in dirs if not d[0] == '.']
            files = [f for f in files if not f[0] == '.']

            # NOTE(flaper87): We could have used shutil.copytree
            # but it requires the dst dir to not be present. This
            # approach is safer as it doesn't require us to delete
            # the output_dir in advance and it allows for running
            # the command multiple times with the same output_dir.
            out_dir = subdir
            if output_dir:
                if template_path != '.':
                    # strip out base path if not default
                    temp = out_dir.split(template_path)[1]
                    out_dir = temp[1:] if temp.startswith('/') else temp
                out_dir = os.path.join(output_dir, out_dir)
                if not os.path.exists(out_dir):
                    os.mkdir(out_dir)

            # Ensure template is on its expected search path
            # for upcoming parsing and rendering
            for f in files:
                if f.endswith('.j2') and output_dir:
                    _shutil_copy_if_not_same(os.path.join(subdir, f), out_dir)

            for f in files:
                file_path = os.path.join(subdir, f)
                # We do three templating passes here:
                # 1. *.role.j2.yaml - we template just the role name
                #    and create multiple files (one per role)
                # 2  *.network.j2.yaml - we template the network name and
                #    data and create multiple files for networks and
                #    network ports (one per network)
                # 3. *.j2.yaml - we template with all roles_data,
                #    and create one file common to all roles
                if f.endswith('.role.j2.yaml'):
                    print("jinja2 rendering role template %s" % f)
                    with open(file_path) as j2_template:
                        template_data = j2_template.read()
                        print("jinja2 rendering roles %s" % ","
                              .join(role_names))
                        for role in role_names:
                            j2_data = {'role': r_map[role]}
                            out_f = "-".join(
                                [role.lower(),
                                 os.path.basename(f).replace('.role.j2.yaml',
                                                             '.yaml')])
                            out_f_path = os.path.join(out_dir, out_f)
                            if ('network/config' in file_path and
                                r_map[role].get('deprecated_nic_config_name')):
                                d_name = r_map[role].get(
                                    'deprecated_nic_config_name')
                                out_f_path = os.path.join(out_dir, d_name)
                            elif ('network/config' in file_path):
                                d_name = "%s.yaml" % role.lower()
                                out_f_path = os.path.join(out_dir, d_name)
                            if not (out_f_path in excl_templates):
                                if '{{role.name}}' in template_data:
                                    j2_data = {'role': r_map[role],
                                               'networks': network_data}
                                    _j2_render_to_file(template_data, j2_data,
                                                       out_f_path, overwrite,
                                                       dry_run)
                                else:
                                    # Backwards compatibility with templates
                                    # that specify {{role}} vs {{role.name}}
                                    j2_data = {'role': role,
                                               'networks': network_data}
                                    _j2_render_to_file(
                                        template_data, j2_data,
                                        out_f_path, overwrite, dry_run)

                            else:
                                print('skipping rendering of %s' % out_f_path)

                elif f.endswith('.network.j2.yaml'):
                    print("jinja2 rendering network template %s" % f)
                    with open(file_path) as j2_template:
                        template_data = j2_template.read()
                    print("jinja2 rendering networks %s" % ",".join(n_map))
                    for network in n_map:
                        j2_data = {'network': n_map[network]}
                        # Output file names in "<name>.yaml" format
                        out_f = os.path.basename(f).replace('.network.j2.yaml',
                                                            '.yaml')
                        if os.path.dirname(file_path).endswith('ports'):
                            out_f = out_f.replace('port',
                                                  n_map[network]['name_lower'])
                        else:
                            out_f = out_f.replace('network',
                                                  n_map[network]['name_lower'])
                        out_f_path = os.path.join(out_dir, out_f)
                        if not (out_f_path in excl_templates):
                            _j2_render_to_file(template_data, j2_data,
                                               out_f_path, overwrite, dry_run)
                        else:
                            print('skipping rendering of %s' % out_f_path)

                elif f.endswith('.j2.yaml'):
                    print("jinja2 rendering normal template %s" % f)
                    with open(file_path) as j2_template:
                        template_data = j2_template.read()
                        j2_data = {'roles': role_data,
                                   'networks': network_data}
                        out_f = os.path.basename(f).replace('.j2.yaml',
                                                            '.yaml')
                        out_f_path = os.path.join(out_dir, out_f)
                        _j2_render_to_file(template_data, j2_data, out_f_path,
                                           overwrite, dry_run)
                elif output_dir:
                    _shutil_copy_if_not_same(os.path.join(subdir, f), out_dir)

    else:
        print('Unexpected argument %s' % template_path)


def clean_templates(base_path, role_data_path, network_data_path):

    def delete(f):
        if os.path.exists(f):
            print("Deleting %s" % f)
            os.unlink(f)

    for root, dirs, files in os.walk(base_path):
        for f in files:
            if f.endswith('.j2.yaml'):
                rendered_path = os.path.join(
                    root, '%s.yaml' % f.split('.j2.yaml')[0])
                delete(rendered_path)

    with open(network_data_path) as network_data_file:
        network_data = yaml.safe_load(network_data_file)

    for network in network_data:
        network_path = os.path.join(
            'network', '%s.yaml' % network['name_lower'])
        network_from_pool_path = os.path.join(
            'network', '%s_from_pool.yaml' % network['name_lower'])
        network_v6_path = os.path.join(
            'network', '%s_v6.yaml' % network['name_lower'])
        network_from_pool_v6_path = os.path.join(
            'network', '%s_from_pool_v6.yaml' % network['name_lower'])
        ports_path = os.path.join(
            'network', 'ports', '%s.yaml' % network['name_lower'])
        external_resource_ports_path = os.path.join(
            'network', 'ports',
            'external_resource_%s.yaml' % network['name_lower'])
        external_resource_ports_v6_path = os.path.join(
            'network', 'ports',
            'external_resource_%s_v6.yaml' % network['name_lower'])
        ports_from_pool_path = os.path.join(
            'network', 'ports', '%s_from_pool.yaml' % network['name_lower'])
        ports_v6_path = os.path.join(
            'network', 'ports', '%s_v6.yaml' % network['name_lower'])
        ports_from_pool_v6_path = os.path.join(
            'network', 'ports', '%s_from_pool_v6.yaml' % network['name_lower'])

        delete(network_path)
        delete(network_from_pool_path)
        delete(network_v6_path)
        delete(network_from_pool_v6_path)
        delete(ports_path)
        delete(external_resource_ports_path)
        delete(external_resource_ports_v6_path)
        delete(ports_from_pool_path)
        delete(ports_v6_path)
        delete(ports_from_pool_v6_path)

    with open(role_data_path) as role_data_file:
        role_data = yaml.safe_load(role_data_file)

    for role in role_data:
        role_path = os.path.join(
            'puppet', '%s-role.yaml' % role['name'].lower())
        host_config_and_reboot_path = os.path.join(
            'extraconfig', 'pre_network',
            '%s-host_config_and_reboot.yaml' % role['name'].lower())
        krb_service_principals_path = os.path.join(
            'extraconfig', 'nova_metadata', 'krb-service-principals',
            '%s-role.yaml' % role['name'].lower())
        common_services_path = os.path.join(
            'common', 'services', '%s-role.yaml' % role['name'].lower())

        delete(role_path)
        delete(host_config_and_reboot_path)
        delete(krb_service_principals_path)
        delete(common_services_path)

        nic_config_dir = os.path.join(base_path, 'network', 'config')
        for sample_nic_config_dir in os.listdir(nic_config_dir):
            delete(os.path.join(
                    nic_config_dir, sample_nic_config_dir,
                    '%s.yaml' % role['name'].lower()))
            if 'deprecated_nic_config_name' in role:
                delete(os.path.join(
                        nic_config_dir, sample_nic_config_dir,
                        role['deprecated_nic_config_name']))


opts = parse_opts(sys.argv)

role_data_path = os.path.join(opts.base_path, opts.roles_data)
network_data_path = os.path.join(opts.base_path, opts.network_data)

if opts.clean:
    clean_templates(opts.base_path, role_data_path, network_data_path)
else:
    process_templates(opts.base_path, role_data_path, opts.output_dir,
                      network_data_path, (not opts.safe), opts.dry_run)
