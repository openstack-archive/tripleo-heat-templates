#!/usr/libexec/platform-python
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
import json
import netaddr
import openstack
import os
import subprocess

CTLPLANE_NETWORK_NAME = 'ctlplane'
CONF = json.loads(os.environ['config'])
CLOUD_DOMAIN = 'ctlplane.' + (CONF['cloud_domain'] + '.'
                              if not CONF['cloud_domain'].endswith('.')
                              else CONF['cloud_domain'])


def _run_command(args, env=None, name=None):
    """Run the command defined by args and return its output

    :param args: List of arguments for the command to be run.
    :param env: Dict defining the environment variables. Pass None to use
        the current environment.
    :param name: User-friendly name for the command being run. A value of
        None will cause args[0] to be used.
    """
    if name is None:
        name = args[0]

    if env is None:
        env = os.environ
    env = env.copy()

    # When running a localized python script, we need to tell it that we're
    # using utf-8 for stdout, otherwise it can't tell because of the pipe.
    env['PYTHONIOENCODING'] = 'utf8'

    try:
        return subprocess.check_output(args,
                                       stderr=subprocess.STDOUT,
                                       env=env).decode('utf-8')
    except subprocess.CalledProcessError as ex:
        print('ERROR: %s failed: %s' % (name, ex.output))
        raise


def _ensure_neutron_network(sdk):
    try:
        network = list(sdk.network.networks(name=CTLPLANE_NETWORK_NAME))
        if not network:
            network = sdk.network.create_network(
                name=CTLPLANE_NETWORK_NAME,
                provider_network_type='flat',
                provider_physical_network=CONF['physical_network'],
                mtu=CONF['mtu'],
                dns_domain=CLOUD_DOMAIN)
            print('INFO: Network created %s' % network)
        else:
            network = sdk.network.update_network(
                network[0].id,
                name=CTLPLANE_NETWORK_NAME,
                mtu=CONF['mtu'],
                dns_domain=CLOUD_DOMAIN)
            print('INFO: Network updated %s' % network)
    except Exception:
        print('ERROR: Network create/update failed.')
        raise

    return network


def _get_nameservers_for_version(servers, ipversion):
    """Get list of nameservers for an IP version"""
    return [s for s in servers if netaddr.IPAddress(s).version == ipversion]


def _neutron_subnet_create(sdk, network_id, cidr, gateway, host_routes,
                           allocation_pools, name, segment_id,
                           dns_nameservers):
    try:
        if netaddr.IPNetwork(cidr).version == 6:
            subnet = sdk.network.create_subnet(
                name=name,
                cidr=cidr,
                gateway_ip=gateway,
                enable_dhcp=True,
                ip_version='6',
                ipv6_address_mode=CONF['ipv6_address_mode'],
                ipv6_ra_mode=CONF['ipv6_address_mode'],
                allocation_pools=allocation_pools,
                network_id=network_id,
                segment_id=segment_id,
                dns_nameservers=_get_nameservers_for_version(dns_nameservers,
                                                             6))
        else:
            subnet = sdk.network.create_subnet(
                name=name,
                cidr=cidr,
                gateway_ip=gateway,
                host_routes=host_routes,
                enable_dhcp=True,
                ip_version='4',
                allocation_pools=allocation_pools,
                network_id=network_id,
                segment_id=segment_id,
                dns_nameservers=_get_nameservers_for_version(dns_nameservers,
                                                             4))
            print('INFO: Subnet created %s' % subnet)
    except Exception:
        print('ERROR: Create subnet %s failed.' % name)
        raise

    return subnet


def _neutron_subnet_update(sdk, subnet_id, cidr, gateway, host_routes,
                           allocation_pools, name, dns_nameservers):
    try:
        if netaddr.IPNetwork(cidr).version == 6:
            subnet = sdk.network.update_subnet(
                subnet_id,
                name=name,
                gateway_ip=gateway,
                allocation_pools=allocation_pools,
                dns_nameservers=_get_nameservers_for_version(dns_nameservers,
                                                             6))
        else:
            subnet = sdk.network.update_subnet(
                subnet_id,
                name=name,
                gateway_ip=gateway,
                host_routes=host_routes,
                allocation_pools=allocation_pools,
                dns_nameservers=_get_nameservers_for_version(dns_nameservers,
                                                             4))
        print('INFO: Subnet updated %s' % subnet)
    except Exception:
        print('ERROR: Update of subnet %s failed.' % name)
        raise


def _neutron_add_subnet_segment_association(sdk, subnet_id, segment_id):
    try:
        subnet = sdk.network.update_subnet(subnet_id, segment_id=segment_id)
        print('INFO: Segment association added to Subnet  %s' % subnet)
    except Exception:
        print('ERROR: Associationg segment with subnet %s failed.' % subnet_id)
        raise


def _neutron_segment_create(sdk, name, network_id, phynet):
    try:
        segment = sdk.network.create_segment(
            name=name,
            network_id=network_id,
            physical_network=phynet,
            network_type='flat')
        print('INFO: Neutron Segment created %s' % segment)
    except Exception:
        print('ERROR: Neutron Segment %s create failed.' % name)
        raise

    return segment


def _neutron_segment_update(sdk, segment_id, name):
    try:
        segment = sdk.network.update_segment(segment_id, name=name)
        print('INFO: Neutron Segment updated %s', segment)
    except Exception:
        print('ERROR: Neutron Segment %s update failed.' % name)
        raise


def _ensure_neutron_router(sdk, subnet):
    try:
        router = sdk.network.find_router(name_or_id=subnet.name)
        if router is None:
            sdk.network.create_router(name=subnet.name,
                                      admin_state_up='true')
    except Exception:
        print('ERROR: Create router for subnet %s failed.' % subnet.name)
        raise


def _add_router_port(sdk, subnet):
    try:
        router = sdk.network.find_router(name_or_id=subnet.name)
        sdk.network.add_interface_to_router(router.id, subnet_id=subnet.id)
    except Exception:
        print('ERROR: Add router port for subnet %s failed.' % subnet.name)
        raise


def _remove_router_port(sdk, subnet):
    try:
        router = sdk.network.find_router(name_or_id=subnet.name)
        if router is None:
            return

        router_port = next(sdk.network.ports(
            network_id=subnet.network_id,
            device_owner='network:router_interface'))
        sdk.network.remove_interface_from_router(router.id, subnet.id,
                                                 router_port.id)
    except StopIteration:
        # There is no router port
        pass
    except Exception:
        print('ERROR: Delete router %s failed.' % subnet.name)
        raise


def _get_subnet(sdk, cidr, network_id):
    try:
        subnet = list(sdk.network.subnets(cidr=cidr, network_id=network_id))
    except Exception:
        print('ERROR: Get subnet with cidr %s failed.' % cidr)
        raise

    return False if not subnet else subnet[0]


def _get_segment(sdk, phy, network_id):
    try:
        segment = list(sdk.network.segments(physical_network=phy,
                                            network_id=network_id))
    except Exception:
        print('ERROR: Get segment for physical_network %s on network_id %s '
              'failed.' % (phy, network_id))
        raise

    return False if not segment else segment[0]


def _set_network_tags(sdk, network, tags):
    try:
        sdk.network.set_tags(network, tags=tags)
        print('INFO: Tags %s added to network %s.' % (tags, network.name))
    except Exception:
        print('ERROR: Setting tags %s on network %s failed.' %
              (tags, network.name))
        raise


def _local_neutron_segments_and_subnets(sdk, ctlplane_id, net_cidrs):
    """Create's and updates the ctlplane subnet on the segment that is local to
    the underclud.
    """
    s = CONF['subnets'][CONF['local_subnet']]
    # If the subnet is IPv6 we need to start a router so that router
    #  advertisements are sent out for stateless IP addressing to work.
    # NOTE(hjensas): Don't do this for routed networks. The router will
    #  use the address defined as gateway for the subnet, and in a
    #  deployment with routed networks this will conflict with the router
    #  in the infrastructure. The router in the infrastructure must be
    #  configured to send router advertisements.
    enable_ipv6_router = (CONF['enable_routed_networks'] is False
                          and netaddr.IPNetwork(s['NetworkCidr']).version == 6)
    name = CONF['local_subnet']
    subnet = _get_subnet(sdk, s['NetworkCidr'], ctlplane_id)
    segment = _get_segment(sdk, CONF['physical_network'], ctlplane_id)

    if subnet:
        if CONF['enable_routed_networks'] and subnet.segment_id is None:
            # The subnet exists and does not have a segment association. Since
            # routed networks is enabled in the configuration, we need to
            # migrate the existing non-routed networks subnet to a routed
            # networks subnet by associating the network segment_id with the
            # subnet.
            _neutron_add_subnet_segment_association(sdk, subnet.id, segment.id)

        # The router interface must be removed prior to updating the subnet
        # in case the gateway_ip of the subnet changed.
        if enable_ipv6_router:
            _remove_router_port(sdk, subnet)

        _neutron_subnet_update(
            sdk, subnet.id, s['NetworkCidr'], s['NetworkGateway'],
            s['HostRoutes'], s.get('AllocationPools'), name,
            s['DnsNameServers'])
    else:
        if CONF['enable_routed_networks']:
            segment_id = segment.id
        else:
            segment_id = None

        subnet = _neutron_subnet_create(
            sdk, ctlplane_id, s['NetworkCidr'], s['NetworkGateway'],
            s['HostRoutes'], s.get('AllocationPools'), name, segment_id,
            s['DnsNameServers'])

    if enable_ipv6_router:
        _ensure_neutron_router(sdk, subnet)
        _add_router_port(sdk, subnet)

    net_cidrs.append(s['NetworkCidr'])

    return net_cidrs


def _remote_neutron_segments_and_subnets(sdk, ctlplane_id, net_cidrs):
    """Create's and updates the ctlplane subnet(s) on segments that is
    not local to the undercloud.
    """

    for name in CONF['subnets']:
        s = CONF['subnets'][name]
        if name == CONF['local_subnet']:
            continue
        phynet = name
        subnet = _get_subnet(sdk, s['NetworkCidr'], ctlplane_id)
        segment = _get_segment(sdk, phynet, ctlplane_id)
        if subnet:
            _neutron_segment_update(sdk, subnet.segment_id, name)
            _neutron_subnet_update(
                sdk, subnet.id, s['NetworkCidr'], s['NetworkGateway'],
                s['HostRoutes'], s.get('AllocationPools'), name,
                s['DnsNameServers'])
        else:
            if segment:
                _neutron_segment_update(sdk, segment.id, name)
            else:
                segment = _neutron_segment_create(sdk, name, ctlplane_id,
                                                  phynet)
            subnet = _neutron_subnet_create(
                sdk, ctlplane_id, s['NetworkCidr'], s['NetworkGateway'],
                s['HostRoutes'], s.get('AllocationPools'), name, segment.id,
                s['DnsNameServers'])
        net_cidrs.append(s['NetworkCidr'])

    return net_cidrs


if 'true' not in _run_command(['hiera', 'neutron_api_enabled'],
                              name='hiera').lower():
    print('WARNING: UndercloudCtlplaneNetworkDeployment : The Neutron API '
          'is disabled. The ctlplane network cannot be configured.')
else:
    sdk = openstack.connect(CONF['cloud_name'])

    network = _ensure_neutron_network(sdk)
    net_cidrs = []
    # Always create/update the local_subnet first to ensure it is can have the
    # subnet associated with a segment prior to creating the remote subnets if
    # the user enabled routed networks support on undercloud update.
    net_cidrs = _local_neutron_segments_and_subnets(sdk, network.id, net_cidrs)
    if CONF['enable_routed_networks']:
        net_cidrs = _remote_neutron_segments_and_subnets(sdk, network.id,
                                                         net_cidrs)
    # Set the cidrs for all ctlplane subnets as tags on the ctlplane network.
    # These tags are used for the NetCidrMapValue in tripleo-heat-templates.
    _set_network_tags(sdk, network, net_cidrs)
