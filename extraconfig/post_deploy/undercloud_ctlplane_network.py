#!/usr/bin/env python

import json
import netaddr
import os
import os_client_config
import subprocess

CTLPLANE_NETWORK_NAME = 'ctlplane'

AUTH_URL = os.environ['auth_url']
ADMIN_PASSWORD = os.environ['admin_password']
CONF = json.loads(os.environ['config'])


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
                mtu=CONF['mtu'])
            print('INFO: Network created %s' % network)
            # (hjensas) Delete the default segment, we create a new segment
            # per subnet later.
            segments = list(sdk.network.segments(network_id=network.id))
            sdk.network.delete_segment(segments[0].id)
            print('INFO: Default segment on network %s deleted.' %
                  network.name)
        else:
            network = sdk.network.update_network(
                network[0].id,
                name=CTLPLANE_NETWORK_NAME,
                mtu=CONF['mtu'])
            print('INFO: Network updated %s' % network)
    except Exception:
        print('ERROR: Network create/update failed.')
        raise

    return network


def _neutron_subnet_create(sdk, network_id, cidr, gateway, host_routes,
                           allocation_pool, name, segment_id, dns_nameservers):
    try:
        if netaddr.IPNetwork(cidr).version == 6:
            subnet = sdk.network.create_subnet(
                name=name,
                cidr=cidr,
                gateway_ip=gateway,
                enable_dhcp=True,
                ip_version='6',
                ipv6_address_mode='dhcpv6-stateless',
                ipv6_ra_mode='dhcpv6-stateless',
                allocation_pools=allocation_pool,
                network_id=network_id,
                segment_id=segment_id,
                dns_nameservers=dns_nameservers)
        else:
            subnet = sdk.network.create_subnet(
                name=name,
                cidr=cidr,
                gateway_ip=gateway,
                host_routes=host_routes,
                enable_dhcp=True,
                ip_version='4',
                allocation_pools=allocation_pool,
                network_id=network_id,
                segment_id=segment_id,
                dns_nameservers=dns_nameservers)
            print('INFO: Subnet created %s' % subnet)
    except Exception:
        print('ERROR: Create subnet %s failed.' % name)
        raise

    return subnet


def _neutron_subnet_update(sdk, subnet_id, cidr, gateway, host_routes,
                           allocation_pool, name, dns_nameservers):
    try:
        if netaddr.IPNetwork(cidr).version == 6:
            subnet = sdk.network.update_subnet(
                subnet_id,
                name=name,
                gateway_ip=gateway,
                allocation_pools=allocation_pool,
                dns_nameservers=dns_nameservers)
        else:
            subnet = sdk.network.update_subnet(
                subnet_id,
                name=name,
                gateway_ip=gateway,
                host_routes=host_routes,
                allocation_pools=allocation_pool,
                dns_nameservers=dns_nameservers)
        print('INFO: Subnet updated %s' % subnet)
    except Exception:
        print('ERROR: Update of subnet %s failed.' % name)
        raise


def _neutron_segment_create(sdk, name, network_id, phynet):
    try:
        segment = sdk.network.create_segment(
            name=name,
            network_id=network_id,
            physical_network=phynet,
            network_type='flat')
        print('INFO: Neutron Segment created %s' % segment)
    except Exception as ex:
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


def _ensure_neutron_router(sdk, name, subnet_id):
    try:
        router = sdk.network.create_router(name=name, admin_state_up='true')
        sdk.network.add_interface_to_router(router.id, subnet_id=subnet_id)
    except Exception:
        print('ERROR: Create router for subnet %s failed.' % name)
        raise


def _get_subnet(sdk, cidr, network_id):
    try:
        subnet = list(sdk.network.subnets(cidr=cidr, network_id=network_id))
    except Exception as ex:
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


def config_neutron_segments_and_subnets(sdk, ctlplane_id):
    s = CONF['subnets'][CONF['local_subnet']]
    subnet = _get_subnet(sdk, s['NetworkCidr'], ctlplane_id)
    if subnet and not subnet.segment_id:
        print('WARNING: Local subnet %s already exists and is not associated '
              'with a network segment. Any additional subnets will be '
              'ignored.' % CONF['local_subnet'])
        host_routes = [{'destination': '169.254.169.254/32',
                        'nexthop': CONF['local_ip']}]
        allocation_pool = [{'start': s['DhcpRangeStart'],
                            'end': s['DhcpRangeEnd']}]
        _neutron_subnet_update(
            sdk, subnet.id, s['NetworkCidr'], s['NetworkGateway'], host_routes,
            allocation_pool, CONF['local_subnet'], CONF['nameservers'])
        # If the subnet is IPv6 we need to start a router so that router
        # advertisments are sent out for stateless IP addressing to work.
        if netaddr.IPNetwork(s['NetworkCidr']).version == 6:
            _ensure_neutron_router(sdk, CONF['local_subnet'], subnet.id)
    else:
        for name in CONF['subnets']:
            s = CONF['subnets'][name]

            phynet = name
            metadata_nexthop = s['NetworkGateway']
            if name == CONF['local_subnet']:
                phynet = CONF['physical_network']
                metadata_nexthop = CONF['local_ip']

            host_routes = [{'destination': '169.254.169.254/32',
                            'nexthop': metadata_nexthop}]
            allocation_pool = [{'start': s['DhcpRangeStart'],
                                'end': s['DhcpRangeEnd']}]

            subnet = _get_subnet(sdk, s['NetworkCidr'], ctlplane_id)
            segment = _get_segment(sdk, phynet, ctlplane_id)

            if name == CONF['local_subnet']:
                if ((subnet and not segment) or
                        (subnet and segment and
                         subnet.segment_id != segment.id)):
                    raise RuntimeError(
                        'The cidr: %s of the local subnet is already used in '
                        'subnet: %s which is associated with segment_id: %s.' %
                        (s['NetworkCidr'], subnet.id, subnet.segment_id))

            if subnet:
                _neutron_segment_update(sdk, subnet.segment_id, name)
                _neutron_subnet_update(
                    sdk, subnet.id, s['NetworkCidr'], s['NetworkGateway'],
                    host_routes, allocation_pool, name, CONF['nameservers'])
            else:
                if segment:
                    _neutron_segment_update(sdk, segment.id, name)
                else:
                    segment = _neutron_segment_create(sdk, name,
                                                      ctlplane_id, phynet)

                if CONF['enable_routed_networks']:
                    subnet = _neutron_subnet_create(
                        sdk, ctlplane_id, s['NetworkCidr'],
                        s['NetworkGateway'], host_routes, allocation_pool,
                        name, segment.id, CONF['nameservers'])
                else:
                    subnet = _neutron_subnet_create(
                        sdk, ctlplane_id, s['NetworkCidr'],
                        s['NetworkGateway'], host_routes, allocation_pool,
                        name, None, CONF['nameservers'])

            # If the subnet is IPv6 we need to start a router so that router
            # advertisments are sent out for stateless IP addressing to work.
            if netaddr.IPNetwork(s['NetworkCidr']).version == 6:
                _ensure_neutron_router(sdk, name, subnet.id)



if _run_command(['hiera', 'neutron_api_enabled'], name='hiera'):
    sdk = os_client_config.make_sdk(auth_url=AUTH_URL,
                                    project_name='admin',
                                    username='admin',
                                    password=ADMIN_PASSWORD,
                                    project_domain_name='Default',
                                    user_domain_name='Default')

    network = _ensure_neutron_network(sdk)
    config_neutron_segments_and_subnets(sdk, network.id)
