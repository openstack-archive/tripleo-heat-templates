# Copyright 2014 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

class tripleo::loadbalancer (
  $keystone_admin     = false,
  $keystone_public    = false,
  $neutron            = false,
  $cinder             = false,
  $glance_api         = false,
  $glance_registry    = false,
  $nova_ec2           = false,
  $nova_osapi         = false,
  $nova_metadata      = false,
  $nova_novncproxy    = false,
  $ceilometer         = false,
  $swift_proxy_server = false,
  $heat_api           = false,
  $heat_cloudwatch    = false,
  $heat_cfn           = false,
  $horizon            = false,
  $mysql              = false,
  $rabbitmq           = false,
) {

  case $::osfamily {
    'RedHat': {
      $keepalived_name_is_process = false
      $keepalived_vrrp_script     = 'systemctl status haproxy.service'
    } # RedHat
    'Debian': {
      $keepalived_name_is_process = true
      $keepalived_vrrp_script     = undef
    }
  }

  class { 'keepalived': }
  keepalived::vrrp_script { 'haproxy':
    name_is_process => $keepalived_name_is_process,
    script          => $keepalived_vrrp_script,
  }

  # KEEPALIVE INSTANCE CONTROL
  keepalived::instance { '51':
    interface     => hiera('control_virtual_interface'),
    virtual_ips   => [join([hiera('controller_virtual_ip'), ' dev ', hiera('control_virtual_interface')])],
    state         => 'MASTER',
    track_script  => ['haproxy'],
    priority      => 101,
  }

  # KEEPALIVE INSTANCE PUBLIC
  keepalived::instance { '52':
    interface     => hiera('public_virtual_interface'),
    virtual_ips   => [join([hiera('public_virtual_ip'), ' dev ', hiera('public_virtual_interface')])],
    state         => 'MASTER',
    track_script  => ['haproxy'],
    priority      => 101,
  }

  sysctl::value { 'net.ipv4.ip_nonlocal_bind': value => '1' }

  class { 'haproxy':
    global_options   => {
      'log'     => '/dev/log local0',
      'pidfile' => '/var/run/haproxy.pid',
      'user'    => 'haproxy',
      'group'   => 'haproxy',
      'daemon'  => '',
      'maxconn' => '4000',
    },
    defaults_options => {
      'mode'    => 'tcp',
      'log'     => 'global',
      'retries' => '3',
      'maxconn' => '150',
      'option'  => [ 'tcpka', 'tcplog' ],
      'timeout' => [ 'http-request 10s', 'queue 1m', 'connect 10s', 'client 1m', 'server 1m', 'check 10s' ],
    },
  }

  haproxy::listen { 'haproxy.stats':
    ipaddress        => '*',
    ports            => '1993',
    mode             => 'http',
    options          => {
      'stats' => 'enable',
    },
    collect_exported => false,
  }

  if $keystone_admin {
    haproxy::listen { 'keystone_admin':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 35357,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'keystone_admin':
      listening_service => 'keystone_admin',
      ports             => '35357',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $keystone_public {
    haproxy::listen { 'keystone_public':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 5000,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'keystone_public':
      listening_service => 'keystone_public',
      ports             => '5000',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $neutron {
    haproxy::listen { 'neutron':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 9696,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'neutron':
      listening_service => 'neutron',
      ports             => '9696',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $cinder {
    haproxy::listen { 'cinder':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8776,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'cinder':
      listening_service => 'cinder',
      ports             => '8776',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $glance_api {
    haproxy::listen { 'glance_api':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 9292,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'glance_api':
      listening_service => 'glance_api',
      ports             => '9292',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }


  if $glance_registry {
    haproxy::listen { 'glance_registry':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 9191,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'glance_registry':
      listening_service => 'glance_registry',
      ports             => '9191',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $nova_ec2 {
    haproxy::listen { 'nova_ec2':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8773,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'nova_ec2':
      listening_service => 'nova_ec2',
      ports             => '8773',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $nova_osapi {
    haproxy::listen { 'nova_osapi':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8774,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'nova_osapi':
      listening_service => 'nova_osapi',
      ports             => '8774',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $nova_metadata {
    haproxy::listen { 'nova_metadata':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8775,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'nova_metadata':
      listening_service => 'nova_metadata',
      ports             => '8775',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $nova_novncproxy {
    haproxy::listen { 'nova_novncproxy':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 6080,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'nova_novncproxy':
      listening_service => 'nova_novncproxy',
      ports             => '6080',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $ceilometer {
    haproxy::listen { 'ceilometer':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8777,
      collect_exported => false,
    }
    haproxy::balancermember { 'ceilometer':
      listening_service => 'ceilometer',
      ports             => '8777',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $swift_proxy_server {
    haproxy::listen { 'swift_proxy_server':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8080,
      options          => { 'option' => [ 'httpchk GET /info' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'swift_proxy_server':
      listening_service => 'swift_proxy_server',
      ports             => '8080',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $heat_api {
    haproxy::listen { 'heat_api':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8004,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'heat_api':
      listening_service => 'heat_api',
      ports             => '8004',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $heat_cloudwatch {
    haproxy::listen { 'heat_cloudwatch':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8003,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'heat_cloudwatch':
      listening_service => 'heat_cloudwatch',
      ports             => '8003',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $heat_cfn {
    haproxy::listen { 'heat_cfn':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 8000,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'heat_cfn':
      listening_service => 'heat_cfn',
      ports             => '8000',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $horizon {
    haproxy::listen { 'horizon':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 80,
      options          => { 'option' => [ 'httpchk GET /' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'horizon':
      listening_service => 'horizon',
      ports             => '80',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $mysql {
    haproxy::listen { 'mysql':
      ipaddress        => [hiera('controller_virtual_ip')],
      ports            => 3306,
      options          => { 'timeout' => [ 'client 0', 'server 0' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'mysql':
      listening_service => 'mysql',
      ports             => '3306',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

  if $rabbitmq {
    haproxy::listen { 'rabbitmq':
      ipaddress        => [hiera('controller_virtual_ip'), hiera('public_virtual_ip')],
      ports            => 5672,
      options          => { 'timeout' => [ 'client 0', 'server 0' ] },
      collect_exported => false,
    }
    haproxy::balancermember { 'rabbitmq':
      listening_service => 'rabbitmq',
      ports             => '5672',
      ipaddresses       => hiera('controller_host'),
      options           => ['check', 'inter 2000', 'rise 2', 'fall 5'],
    }
  }

}

include ::tripleo::loadbalancer
