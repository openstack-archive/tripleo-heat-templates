#!/bin/bash

KOLLA_DEST=/var/lib/kolla/config_files
JSON_DEST=/var/lib/etc-data/json-config

# For more config file generation, simply define a new SERVICE_DATA_
# prefixed variable. The command string is quoted to include config-file
# arguments. Note that the variable name following SERVICE_DATA_ will be
# the filename the JSON config is written to.

# [EXAMPLE]: SERVICE_DATA_<SERVICE_NAME>=(<command> <source> <dest> <owner> <perms>)

SERVICE_DATA_NOVA_LIBVIRT=("/usr/sbin/libvirtd" libvirtd.conf /etc/libvirt/libvirtd.conf root 0644)
SERVICE_DATA_NOVA_COMPUTE=("/usr/bin/nova-compute" nova.conf /etc/nova/nova.conf nova 0600)
SERVICE_DATA_NEUTRON_OPENVSWITCH_AGENT=("/usr/bin/neutron-openvswitch-agent --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini" neutron.conf /etc/neutron/neutron.conf neutron 0600 ml2_conf.ini /etc/neutron/plugins/ml2/ml2_conf.ini neutron 0600)
SERVICE_DATA_NEUTRON_AGENT=("/usr/bin/neutron-openvswitch-agent --config-file /usr/share/neutron/neutron-dist.conf --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini" neutron.conf /etc/neutron/neutron.conf neutron 0600 ovs_neutron_plugin.ini /etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini neutron 0600)
SERVICE_DATA_OVS_VSWITCHD=("/usr/sbin/ovs-vswitchd unix:/run/openvswitch/db.sock -vconsole:emer -vsyslog:err -vfile:info --mlockall --log-file=/var/log/openvswitch/ovs-vswitchd.log")
SERVICE_DATA_OVS_DBSERVER=("/usr/sbin/ovsdb-server /etc/openvswitch/conf.db -vconsole:emer -vsyslog:err -vfile:info --remote=punix:/run/openvswitch/db.sock --log-file=/var/log/openvswitch/ovsdb-server.log")

function create_json_header() {
    local command=$1

    echo "\
{
    \"command\": \"${command[@]}\","

}

function create_config_file_header() {
    echo "    \"config_files\": ["
}

function create_config_file_block() {
    local source=$KOLLA_DEST/$1
    local dest=$2
    local owner=$3
    local perm=$4

    printf "\
\t{
\t    \"source\": \"$source\",
\t    \"dest\": \"$dest\",
\t    \"owner\": \"$owner\",
\t    \"perm\": \"$perm\"
\t}"
}

function add_trailing_comma() {
    printf ", \n"
}

function create_config_file_trailer() {
    echo -e "\n    ]"
}

function create_json_trailer() {
    echo "}"
}

function create_json_data() {
    local config_data=$1
    shift

    create_json_header "$config_data"
    create_config_file_header
    while [ "$1" ]; do
        create_config_file_block "$@"
        shift 4
        if [ "$1" ]; then
            add_trailing_comma
        fi
    done
    create_config_file_trailer
    create_json_trailer
}

function write_json_data() {

    local name=$1[@]
    local service_data=("${!name}")

    local service_name=${1#SERVICE_DATA_} # chop SERVICE_DATA_ prefix
    service_name=${service_name//_/-}     # switch underscore to dash
    service_name=${service_name,,}        # change to lowercase

    echo "Creating JSON file ${service_name}"
    create_json_data "${service_data[@]}" > "$JSON_DEST/$service_name.json"
}

function process_configs() {
    for service in ${!SERVICE_DATA_*}; do
        write_json_data "${service}"
    done
}

process_configs
