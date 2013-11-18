import os
import sys
import yaml
import argparse


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
    if item == {'Ref': param}:
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
    args = parser.parse_args(argv)
    templates = args.templates
    merged_template = merge(templates, args.master_role, args.slave_roles)
    sys.stdout.write(merged_template)

def merge(templates, master_role=None, slave_roles=None):
    errors = []
    end_template={'HeatTemplateFormatVersion': '2012-12-12',
                  'Description': []}
    resource_changes=[]
    for template_path in templates:
        template = yaml.safe_load(open(template_path))
        # Resolve __include__ tags
        template = resolve_includes(template)
        end_template['Description'].append(template.get('Description',
                                                        template_path))
        new_parameters = template.get('Parameters', {})
        for p, pbody in sorted(new_parameters.items()):
            if p in end_template.get('Parameters', {}):
                if pbody != end_template['Parameters'][p]:
                    errors.append('Parameter %s from %s conflicts.' % (p,
                                                                       template_path))
                continue
            if 'Parameters' not in end_template:
                end_template['Parameters'] = {}
            end_template['Parameters'][p] = pbody

        new_outputs = template.get('Outputs', {})
        for o, obody in sorted(new_outputs.items()):
            if o in end_template.get('Outputs', {}):
                if pbody != end_template['Outputs'][p]:
                    errors.append('Output %s from %s conflicts.' % (o,
                                                                       template_path))
                continue
            if 'Outputs' not in end_template:
                end_template['Outputs'] = {}
            end_template['Outputs'][o] = obody

        new_resources = template.get('Resources', {})
        for r, rbody in sorted(new_resources.items()):
            if rbody['Type'] in MERGABLE_TYPES:
                if 'image' in MERGABLE_TYPES[rbody['Type']]:
                    image_key = MERGABLE_TYPES[rbody['Type']]['image']
                    # XXX Assuming ImageId is always a Ref
                    ikey_val = end_template['Parameters'][rbody['Properties'][image_key]['Ref']]
                    del end_template['Parameters'][rbody['Properties'][image_key]['Ref']]
                role = rbody.get('Metadata', {}).get('OpenStack::Role', r)
                role = translate_role(role, master_role, slave_roles)
                if role != r:
                    resource_changes.append((r, role))
                if role in end_template.get('Resources', {}):
                    new_metadata = rbody.get('Metadata', {})
                    for m, mbody in iter(new_metadata.items()):
                        if m in end_template['Resources'][role].get('Metadata', {}):
                            if m == 'OpenStack::ImageBuilder::Elements':
                                end_template['Resources'][role]['Metadata'][m].extend(mbody)
                                continue
                            if mbody != end_template['Resources'][role]['Metadata'][m]:
                                errors.append('Role %s metadata key %s conflicts.' %
                                              (role, m))
                            continue
                        end_template['Resources'][role]['Metadata'][m] = mbody
                    continue
                if 'Resources' not in end_template:
                    end_template['Resources'] = {}
                end_template['Resources'][role] = rbody
                if 'image' in MERGABLE_TYPES[rbody['Type']]:
                    ikey = '%sImage' % (role)
                    end_template['Resources'][role]['Properties'][image_key] = {'Ref': ikey}
                    end_template['Parameters'][ikey] = ikey_val
            elif rbody['Type'] == 'FileInclude':
                #make sure rbody['Path'] is absolute - required when this
                #script invoked by import rather than command line
                if os.path.dirname(rbody['Path']) == '':
                    template_dir = os.path.dirname(__file__)
                    filename = rbody['Path']
                    rbody['Path'] = os.path.join(template_dir, filename)
                with open(rbody['Path']) as rfile:
                    include_content = yaml.safe_load(rfile.read())
                    subkeys = rbody.get('SubKey','').split('.')
                    while len(subkeys) and subkeys[0]:
                        include_content = include_content[subkeys.pop(0)]
                    for replace_param, replace_value in iter(rbody.get('Parameters',
                                                                       {}).items()):
                        include_content = resolve_params(include_content,
                                                         replace_param,
                                                         replace_value)
                    end_template['Resources'][r] = include_content
            else:
                if r in end_template.get('Resources', {}):
                    if rbody != end_template['Resources'][r]:
                        errors.append('Resource %s from %s conflicts' % (r,
                                                                         template_path))
                    continue
                if 'Resources' not in end_template:
                    end_template['Resources'] = {}
                end_template['Resources'][r] = rbody

    def fix_ref(item, old, new):
        if isinstance(item, dict):
            copy_item = dict(item)
            for k, v in sorted(copy_item.items()):
                if k == 'Ref' and v == old:
                    item[k] = new
                    continue
                if k == 'DependsOn' and v == old:
                    item[k] = new
                    continue
                if k == 'Fn::GetAtt' and isinstance(v, list) and v[0] == old:
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
    end_template['Description'] = ','.join(end_template['Description'])
    return yaml.safe_dump(end_template, default_flow_style=False)

if __name__ == "__main__":
      main()
