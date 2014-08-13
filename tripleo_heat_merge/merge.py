import os
import sys
import yaml
import argparse


class Cfn(object):

    base_template = {
        'HeatTemplateFormatVersion': '2012-12-12',
        'Description': []
    }
    get_resource = 'Ref'
    get_param = 'Ref'
    description = 'Description'
    parameters = 'Parameters'
    outputs = 'Outputs'
    resources = 'Resources'
    type = 'Type'
    properties = 'Properties'
    metadata = 'Metadata'
    depends_on = 'DependsOn'
    get_attr = 'Fn::GetAtt'


class Hot(object):

    base_template = {
        'heat_template_version': '2013-05-23',
        'description': []
    }
    get_resource = 'get_resource'
    get_param = 'get_param'
    description = 'description'
    parameters = 'parameters'
    outputs = 'outputs'
    resources = 'resources'
    type = 'type'
    properties = 'properties'
    metadata = 'metadata'
    depends_on = 'depends_on'
    get_attr = 'get_attr'


lang = Cfn()


def apply_maps(template):
    """Apply Merge::Map within template.

    Any dict {'Merge::Map': {'Foo': 'Bar', 'Baz': 'Quux'}}
    will resolve to ['Bar', 'Quux'] - that is a dict with key
    'Merge::Map' is replaced entirely by that dict['Merge::Map'].values().
    """
    if isinstance(template, dict):
        if 'Merge::Map' in template:
            return sorted(
                apply_maps(value) for value in template['Merge::Map'].values()
                )
        else:
            return dict((key, apply_maps(value))
                for key, value in template.items())
    elif isinstance(template, list):
        return [apply_maps(item) for item in template]
    else:
        return template


def apply_scaling(template, scaling, in_copies=None):
    """Apply a set of scaling operations to template.

    This is a single pass recursive function: for each call we process one
    dict or list and recurse to handle children containers.

    Values are handled via scale_value.

    Keys in dicts are copied per the scaling rule.
    Values are either replaced or copied depending on whether the given
    scaling rule is in in_copies.

    in_copies is reset to None when a dict {'Merge::Map': someobject} is
    encountered.

    :param scaling: A dict of prefix -> (count, blacklists).
    """
    in_copies = dict(in_copies or {})
    # Shouldn't be needed but to avoid unexpected side effects/bugs we short
    # circuit no-ops.
    if not scaling:
        return template
    if isinstance(template, dict):
        if 'Merge::Map' in template:
            in_copies = None
        new_template = {}
        for key, value in template.items():
            for prefix, copy_num, new_key in scale_value(
                key, scaling, in_copies):
                if prefix:
                    # e.g. Compute0, 1, Compute1Foo
                    in_copies[prefix] = prefix[:-1] + str(copy_num)
                if isinstance(value, (dict, list)):
                    new_value = apply_scaling(value, scaling, in_copies)
                    new_template[new_key] = new_value
                else:
                    new_values = list(scale_value(value, scaling, in_copies))
                    # We have nowhere to multiply a non-container value of a
                    # dict, so it may be copied or unchanged but not scaled.
                    assert len(new_values) == 1
                    new_template[new_key] = new_values[0][2]
                if prefix:
                    del in_copies[prefix]
        return new_template
    elif isinstance(template, list):
        new_template = []
        for value in template:
            if isinstance(value, (dict, list)):
                new_template.append(apply_scaling(value, scaling, in_copies))
            else:
                for _, _, new_value in scale_value(value, scaling, in_copies):
                    new_template.append(new_value)
        return new_template
    else:
        raise Exception("apply_scaling called with non-container %r" % template)


def scale_value(value, scaling, in_copies):
    """Scale out a value.

    :param value: The value to scale (not a container).
    :param scaling: The scaling map (prefix-> (copies, blacklist) to use.
    :param in_copies: What containers we're currently copying.
    :return: An iterator of the new values for the value as tuples:
        (prefix, copy_num, value). E.g. Compute0, 1, Compute1Foo
        prefix and copy_num are only set when:
         - a prefix in scaling matches value
         - and that prefix is not in in_copies
    """
    if isinstance(value, (str, unicode)):
        for prefix, (copies, blacklist) in scaling.items():
            if not value.startswith(prefix):
                continue
            suffix = value[len(prefix):]
            if prefix in in_copies:
                # Adjust to the copy number we're on
                yield None, None, in_copies[prefix] + suffix
                return
            else:
                for n in range(copies):
                    if n not in blacklist:
                        yield prefix, n, prefix[:-1] + str(n) + suffix
                return
        yield None, None, value
    else:
        yield None, None, value


def parse_scaling(scaling_args):
    """Translate a list of scaling requests to a dict prefix:count."""
    scaling_args = scaling_args or []
    result = {}
    for item in scaling_args:
        key, values = item.split('=')
        values = values.split(',')
        value = int(values[0])
        blacklist = frozenset(int(v) for v in values[1:] if v)
        result[key + '0'] = value, blacklist
    return result


def _translate_role(role, master_role, slave_roles):
    if not master_role:
        return role
    if role == master_role:
        return role
    if role not in slave_roles:
        return role
    return master_role

def translate_role(role, master_role, slave_roles):
    r = _translate_role(role, master_role, slave_roles)
    if not isinstance(r, basestring):
        raise Exception('%s -> %r' % (role, r))
    return r

def resolve_params(item, param, value):
    if item in ({lang.get_param: param}, {lang.get_resource: param}):
        return value
    if isinstance(item, dict):
        copy_item = dict(item)
        for k, v in iter(copy_item.items()):
            item[k] = resolve_params(v, param, value)
    elif isinstance(item, list):
        copy_item = list(item)
        new_item = []
        for v in copy_item:
            new_item.append(resolve_params(v, param, value))
        item = new_item
    return item

MERGABLE_TYPES = {'OS::Nova::Server':
                  {'image': 'image'},
                  'AWS::EC2::Instance':
                  {'image': 'ImageId'},
                  'AWS::AutoScaling::LaunchConfiguration':
                  {},
                 }
INCLUDED_TEMPLATE_DIR = os.getcwd()


def resolve_includes(template, params=None):
    new_template = {}
    if params is None:
        params = {}
    for key, value in iter(template.items()):
        if key == '__include__':
            new_params = dict(params) # do not propagate up the stack
            if not isinstance(value, dict):
                raise ValueError('__include__ must be a mapping')
            if 'path' not in value:
                raise ValueError('__include__ must have path')
            if 'params' in value:
                if not isinstance(value['params'], dict):
                    raise ValueError('__include__ params must be a mapping')
                new_params.update(value['params'])
            with open(value['path']) as include_file:
                sub_template = yaml.safe_load(include_file.read())
                if 'subkey' in value:
                    if ((not isinstance(value['subkey'], int)
                         and not isinstance(sub_template, dict))):
                        raise RuntimeError('subkey requires mapping root or'
                                           ' integer for list root')
                    sub_template = sub_template[value['subkey']]
                for k, v in iter(new_params.items()):
                    sub_template = resolve_params(sub_template, k, v)
                new_template.update(resolve_includes(sub_template))
        else:
            if isinstance(value, dict):
                new_template[key] = resolve_includes(value)
            else:
                new_template[key] = value
    return new_template

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.add_argument('templates', nargs='+')
    parser.add_argument('--master-role', nargs='?',
                        help='Translate slave_roles to this')
    parser.add_argument('--slave-roles', nargs='*',
                        help='Translate all of these to master_role')
    parser.add_argument('--included-template-dir', nargs='?',
                        default=INCLUDED_TEMPLATE_DIR,
                        help='Path for resolving included templates')
    parser.add_argument('--output',
                        help='File to write output to. - for stdout',
                        default='-')
    parser.add_argument('--scale', action="append",
        help="Names to scale out. Pass Prefix=2 to cause a key Prefix0Foo to "
        "be copied to Prefix1Foo in the output, and value Prefix0Bar to be"
        "renamed to Prefix1Bar inside that copy, or copied to Prefix1Bar "
        "outside of any copy. Pass Prefix=3,1 to cause Prefix1* to be elided"
        "when scaling Prefix out. Prefix=4,1,2 will likewise elide Prefix1 and"
        "Prefix2.")
    parser.add_argument(
        '--change-image-params', action='store_true', default=False,
        help="Change parameters in templates to match resource names. This was "
             " the default at one time but it causes issues when parameter "
             " names need to remain stable.")
    parser.add_argument(
        '--hot', action='store_true', default=False,
        help="Assume source templates are in the HOT format, and generate a "
             "HOT template artifact.")
    args = parser.parse_args(argv)
    if args.hot:
        global lang
        lang = Hot()

    templates = args.templates
    scaling = parse_scaling(args.scale)
    merged_template = merge(templates, args.master_role, args.slave_roles,
                            args.included_template_dir, scaling=scaling,
                            change_image_params=args.change_image_params)
    if args.output == '-':
        out_file = sys.stdout
    else:
        out_file = file(args.output, 'wt')
    out_file.write(merged_template)


def merge(templates, master_role=None, slave_roles=None,
          included_template_dir=INCLUDED_TEMPLATE_DIR,
          scaling=None, change_image_params=None):
    scaling = scaling or {}
    errors = []
    end_template = dict(lang.base_template)
    resource_changes=[]
    for template_path in templates:
        template = yaml.safe_load(open(template_path))
        # Resolve __include__ tags
        template = resolve_includes(template)
        end_template[lang.description].append(template.get(lang.description,
                                                        template_path))
        new_parameters = template.get(lang.parameters, {})
        for p, pbody in sorted(new_parameters.items()):
            if p in end_template.get(lang.parameters, {}):
                if pbody != end_template[lang.parameters][p]:
                    errors.append('Parameter %s from %s conflicts.' % (p,
                                                                       template_path))
                continue
            if lang.parameters not in end_template:
                end_template[lang.parameters] = {}
            end_template[lang.parameters][p] = pbody

        new_outputs = template.get(lang.outputs, {})
        for o, obody in sorted(new_outputs.items()):
            if o in end_template.get(lang.outputs, {}):
                if pbody != end_template[lang.outputs][p]:
                    errors.append('Output %s from %s conflicts.' % (o,
                                                                       template_path))
                continue
            if lang.outputs not in end_template:
                end_template[lang.outputs] = {}
            end_template[lang.outputs][o] = obody

        new_resources = template.get(lang.resources, {})
        for r, rbody in sorted(new_resources.items()):
            if rbody[lang.type] in MERGABLE_TYPES:
                if change_image_params:
                    if 'image' in MERGABLE_TYPES[rbody[lang.type]]:
                        image_key = MERGABLE_TYPES[rbody[lang.type]]['image']
                        # XXX Assuming ImageId is always a Ref
                        ikey_val = end_template[lang.parameters][rbody[lang.properties][image_key][lang.get_param]]
                        del end_template[lang.parameters][rbody[lang.properties][image_key][lang.get_param]]
                role = rbody.get(lang.metadata, {}).get('OpenStack::Role', r)
                role = translate_role(role, master_role, slave_roles)
                if role != r:
                    resource_changes.append((r, role))
                if role in end_template.get(lang.resources, {}):
                    new_metadata = rbody.get(lang.metadata, {})
                    for m, mbody in iter(new_metadata.items()):
                        if m in end_template[lang.resources][role].get(lang.metadata, {}):
                            if m == 'OpenStack::ImageBuilder::Elements':
                                end_template[lang.resources][role][lang.metadata][m].extend(mbody)
                                continue
                            if mbody != end_template[lang.resources][role][lang.metadata][m]:
                                errors.append('Role %s metadata key %s conflicts.' %
                                              (role, m))
                            continue
                        role_res = end_template[lang.resources][role]
                        if role_res[lang.type] == 'OS::Heat::StructuredConfig':
                            end_template[lang.resources][role][lang.properties]['config'][m] = mbody
                        else:
                            end_template[lang.resources][role][lang.metadata][m] = mbody
                    continue
                if lang.resources not in end_template:
                    end_template[lang.resources] = {}
                end_template[lang.resources][role] = rbody
                if change_image_params:
                    if 'image' in MERGABLE_TYPES[rbody[lang.type]]:
                        ikey = '%sImage' % (role)
                        end_template[lang.resources][role][lang.properties][image_key] = {lang.get_param: ikey}
                        end_template[lang.parameters][ikey] = ikey_val
            elif rbody[lang.type] == 'FileInclude':
                # we trust os.path.join to DTRT: if FileInclude path isn't
                # absolute, join to included_template_dir (./)
                with open(os.path.join(included_template_dir, rbody['Path'])) as rfile:
                    include_content = yaml.safe_load(rfile.read())
                    subkeys = rbody.get('SubKey','').split('.')
                    while len(subkeys) and subkeys[0]:
                        include_content = include_content[subkeys.pop(0)]
                    for replace_param, replace_value in iter(rbody.get(lang.parameters,
                                                                       {}).items()):
                        include_content = resolve_params(include_content,
                                                         replace_param,
                                                         replace_value)
                    if lang.resources not in end_template:
                        end_template[lang.resources] = {}
                    end_template[lang.resources][r] = include_content
            else:
                if r in end_template.get(lang.resources, {}):
                    if rbody != end_template[lang.resources][r]:
                        errors.append('Resource %s from %s conflicts' % (r,
                                                                         template_path))
                    continue
                if lang.resources not in end_template:
                    end_template[lang.resources] = {}
                end_template[lang.resources][r] = rbody

    end_template = apply_scaling(end_template, scaling)
    end_template = apply_maps(end_template)

    def fix_ref(item, old, new):
        if isinstance(item, dict):
            copy_item = dict(item)
            for k, v in sorted(copy_item.items()):
                if k == lang.get_resource and v == old:
                    item[k] = new
                    continue
                if k == lang.depends_on and v == old:
                    item[k] = new
                    continue
                if k == lang.get_attr and isinstance(v, list) and v[0] == old:
                    new_list = list(v)
                    new_list[0] = new
                    item[k] = new_list
                    continue
                if k == 'AllowedResources' and isinstance(v, list) and old in v:
                    while old in v:
                        pos = v.index(old)
                        v[pos] = new
                    continue
                fix_ref(v, old, new)
        elif isinstance(item, list):
            copy_item = list(item)
            for v in item:
                fix_ref(v, old, new)

    for change in resource_changes:
        fix_ref(end_template, change[0], change[1])

    if errors:
        for e in errors:
            sys.stderr.write("ERROR: %s\n" % e)
    end_template[lang.description] = ','.join(end_template[lang.description])
    return yaml.safe_dump(end_template, default_flow_style=False)

if __name__ == "__main__":
      main()
