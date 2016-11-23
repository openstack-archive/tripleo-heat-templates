#!/bin/python
import json
import os

data = {}
file_perms = '0600'
libvirt_perms = '0644'

libvirt_config = os.getenv('libvirt_config').split(',')
nova_config = os.getenv('nova_config').split(',')
neutron_openvswitch_agent_config = os.getenv('neutron_openvswitch_agent_config').split(',')

# Command, Config_files, Owner, Perms
services = {
    'nova-libvirt': [
        '/usr/sbin/libvirtd',
        libvirt_config,
        'root',
        libvirt_perms],
    'nova-compute': [
        '/usr/bin/nova-compute',
        nova_config,
        'nova',
        file_perms],
    'neutron-openvswitch-agent': [
        '/usr/bin/neutron-openvswitch-agent',
        neutron_openvswitch_agent_config,
        'neutron',
        file_perms],
    'ovs-vswitchd': [
        '/usr/sbin/ovs-vswitchd unix:/run/openvswitch/db.sock -vconsole:emer -vsyslog:err -vfile:info --mlockall --log-file=/var/log/kolla/openvswitch/ovs-vswitchd.log'],
    'ovsdb-server': [
        '/usr/sbin/ovsdb-server /etc/openvswitch/conf.db -vconsole:emer -vsyslog:err -vfile:info --remote=punix:/run/openvswitch/db.sock --remote=ptcp:6640:127.0.0.1 --log-file=/var/log/kolla/openvswitch/ovsdb-server.log']
}


def build_config_files(config, owner, perms):
    config_source = '/var/lib/kolla/config_files/'
    config_files_dict = {}
    source = os.path.basename(config)
    dest = config
    config_files_dict.update({'source': config_source + source,
                              'dest': dest,
                              'owner': owner,
                              'perm': perms})
    return config_files_dict


for service in services:
    if service != 'ovs-vswitchd' and service != 'ovsdb-server':
        command = services.get(service)[0]
        config_files = services.get(service)[1]
        owner = services.get(service)[2]
        perms = services.get(service)[3]
        config_files_list = []
        for config_file in config_files:
            if service == 'nova-libvirt':
                command = command + ' --config ' + config_file
            else:
                command = command + ' --config-file ' + config_file
            data['command'] = command
            config_files_dict = build_config_files(config_file, owner, perms)
            config_files_list.append(config_files_dict)
        data['config_files'] = config_files_list
    else:
        data['command'] = services.get(service)[0]
        data['config_files'] = []

    json_config_dir = '/var/lib/etc-data/json-config/'
    with open(json_config_dir + service + '.json', 'w') as json_file:
        json.dump(data, json_file, sort_keys=True, indent=4,
                  separators=(',', ': '))
