#!/usr/bin/env python
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# Shell script tool to run puppet inside of the given docker container image.
# Uses the config file at /var/lib/docker-puppet/docker-puppet.json as a source for a JSON
# array of [config_volume, puppet_tags, manifest, config_image, [volumes]] settings
# that can be used to generate config files or run ad-hoc puppet modules
# inside of a container.

import glob
import json
import logging
import os
import sys
import subprocess
import sys
import tempfile
import multiprocessing

log = logging.getLogger()
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

# this is to match what we do in deployed-server
def short_hostname():
    subproc = subprocess.Popen(['hostname', '-s'],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    cmd_stdout, cmd_stderr = subproc.communicate()
    return cmd_stdout.rstrip()


def pull_image(name):
    log.info('Pulling image: %s' % name)
    subproc = subprocess.Popen(['/usr/bin/docker', 'pull', name],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    cmd_stdout, cmd_stderr = subproc.communicate()
    if cmd_stdout:
        log.debug(cmd_stdout)
    if cmd_stderr:
        log.debug(cmd_stderr)


def match_config_volume(prefix, config):
    # Match the mounted config volume - we can't just use the
    # key as e.g "novacomute" consumes config-data/nova
    volumes = config.get('volumes', [])
    config_volume=None
    for v in volumes:
        if v.startswith(prefix):
            config_volume =  os.path.relpath(
                v.split(":")[0], prefix).split("/")[0]
            break
    return config_volume


def get_config_hash(prefix, config_volume):
    hashfile = os.path.join(prefix, "%s.md5sum" % config_volume)
    hash_data = None
    if os.path.isfile(hashfile):
        with open(hashfile) as f:
            hash_data = f.read().rstrip()
    return hash_data


def rm_container(name):
    if os.environ.get('SHOW_DIFF', None):
        log.info('Diffing container: %s' % name)
        subproc = subprocess.Popen(['/usr/bin/docker', 'diff', name],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        cmd_stdout, cmd_stderr = subproc.communicate()
        if cmd_stdout:
            log.debug(cmd_stdout)
        if cmd_stderr:
            log.debug(cmd_stderr)

    log.info('Removing container: %s' % name)
    subproc = subprocess.Popen(['/usr/bin/docker', 'rm', name],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    cmd_stdout, cmd_stderr = subproc.communicate()
    if cmd_stdout:
        log.debug(cmd_stdout)
    if cmd_stderr and \
           cmd_stderr != 'Error response from daemon: ' \
           'No such container: {}\n'.format(name):
        log.debug(cmd_stderr)

process_count = int(os.environ.get('PROCESS_COUNT',
                                   multiprocessing.cpu_count()))

log.info('Running docker-puppet')
config_file = os.environ.get('CONFIG', '/var/lib/docker-puppet/docker-puppet.json')
log.debug('CONFIG: %s' % config_file)
with open(config_file) as f:
    json_data = json.load(f)

# To save time we support configuring 'shared' services at the same
# time. For example configuring all of the heat services
# in a single container pass makes sense and will save some time.
# To support this we merge shared settings together here.
#
# We key off of config_volume as this should be the same for a
# given group of services.  We are also now specifying the container
# in which the services should be configured.  This should match
# in all instances where the volume name is also the same.

configs = {}

for service in (json_data or []):
    if service is None:
        continue
    if isinstance(service, dict):
        service = [
            service.get('config_volume'),
            service.get('puppet_tags'),
            service.get('step_config'),
            service.get('config_image'),
            service.get('volumes', []),
        ]

    config_volume = service[0] or ''
    puppet_tags = service[1] or ''
    manifest = service[2] or ''
    config_image = service[3] or ''
    volumes = service[4] if len(service) > 4 else []

    if not manifest or not config_image:
        continue

    log.debug('config_volume %s' % config_volume)
    log.debug('puppet_tags %s' % puppet_tags)
    log.debug('manifest %s' % manifest)
    log.debug('config_image %s' % config_image)
    log.debug('volumes %s' % volumes)
    # We key off of config volume for all configs.
    if config_volume in configs:
        # Append puppet tags and manifest.
        log.info("Existing service, appending puppet tags and manifest")
        if puppet_tags:
            configs[config_volume][1] = '%s,%s' % (configs[config_volume][1],
                                                   puppet_tags)
        if manifest:
            configs[config_volume][2] = '%s\n%s' % (configs[config_volume][2],
                                                    manifest)
        if configs[config_volume][3] != config_image:
            log.warn("Config containers do not match even though"
                     " shared volumes are the same!")
    else:
        log.info("Adding new service")
        configs[config_volume] = service

log.info('Service compilation completed.')

def mp_puppet_config((config_volume, puppet_tags, manifest, config_image, volumes)):

    log.debug('config_volume %s' % config_volume)
    log.debug('puppet_tags %s' % puppet_tags)
    log.debug('manifest %s' % manifest)
    log.debug('config_image %s' % config_image)
    log.debug('volumes %s' % volumes)
    sh_script = '/var/lib/docker-puppet/docker-puppet.sh'

    with open(sh_script, 'w') as script_file:
        os.chmod(script_file.name, 0755)
        script_file.write("""#!/bin/bash
        set -ex
        mkdir -p /etc/puppet
        cp -a /tmp/puppet-etc/* /etc/puppet
        rm -Rf /etc/puppet/ssl # not in use and causes permission errors
        echo "{\\"step\\": $STEP}" > /etc/puppet/hieradata/docker.json
        TAGS=""
        if [ -n "$PUPPET_TAGS" ]; then
            TAGS="--tags \"$PUPPET_TAGS\""
        fi
        FACTER_hostname=$HOSTNAME FACTER_uuid=docker /usr/bin/puppet apply --verbose $TAGS /etc/config.pp

        # Disables archiving
        if [ -z "$NO_ARCHIVE" ]; then
            rm -Rf /var/lib/config-data/${NAME}

            # copying etc should be enough for most services
            mkdir -p /var/lib/config-data/${NAME}/etc
            cp -a /etc/* /var/lib/config-data/${NAME}/etc/

            # workaround LP1696283
            mkdir -p /var/lib/config-data/${NAME}/etc/ssh
            touch /var/lib/config-data/${NAME}/etc/ssh/ssh_known_hosts

            if [ -d /root/ ]; then
              cp -a /root/ /var/lib/config-data/${NAME}/root/
            fi
            if [ -d /var/lib/ironic/tftpboot/ ]; then
              mkdir -p /var/lib/config-data/${NAME}/var/lib/ironic/
              cp -a /var/lib/ironic/tftpboot/ /var/lib/config-data/${NAME}/var/lib/ironic/tftpboot/
            fi
            if [ -d /var/lib/ironic/httpboot/ ]; then
              mkdir -p /var/lib/config-data/${NAME}/var/lib/ironic/
              cp -a /var/lib/ironic/httpboot/ /var/lib/config-data/${NAME}/var/lib/ironic/httpboot/
            fi

            # apache services may files placed in /var/www/
            if [ -d /var/www/ ]; then
             mkdir -p /var/lib/config-data/${NAME}/var/www
             cp -a /var/www/* /var/lib/config-data/${NAME}/var/www/
            fi

            # Write a checksum of the config-data dir, this is used as a
            # salt to trigger container restart when the config changes
            tar cf - /var/lib/config-data/${NAME} | md5sum | awk '{print $1}' > /var/lib/config-data/${NAME}.md5sum
        fi
        """)

    with tempfile.NamedTemporaryFile() as tmp_man:
        with open(tmp_man.name, 'w') as man_file:
            man_file.write('include ::tripleo::packages\n')
            man_file.write(manifest)

        rm_container('docker-puppet-%s' % config_volume)
        pull_image(config_image)

        dcmd = ['/usr/bin/docker', 'run',
                '--user', 'root',
                '--name', 'docker-puppet-%s' % config_volume,
                '--env', 'PUPPET_TAGS=%s' % puppet_tags,
                '--env', 'NAME=%s' % config_volume,
                '--env', 'HOSTNAME=%s' % short_hostname(),
                '--env', 'NO_ARCHIVE=%s' % os.environ.get('NO_ARCHIVE', ''),
                '--env', 'STEP=%s' % os.environ.get('STEP', '6'),
                '--volume', '%s:/etc/config.pp:ro' % tmp_man.name,
                '--volume', '/etc/puppet/:/tmp/puppet-etc/:ro',
                '--volume', '/usr/share/openstack-puppet/modules/:/usr/share/openstack-puppet/modules/:ro',
                '--volume', '/var/lib/config-data/:/var/lib/config-data/:rw',
                '--volume', 'tripleo_logs:/var/log/tripleo/',
                # OpenSSL trusted CA injection
                '--volume', '/etc/pki/ca-trust/extracted:/etc/pki/ca-trust/extracted:ro',
                '--volume', '/etc/pki/tls/certs/ca-bundle.crt:/etc/pki/tls/certs/ca-bundle.crt:ro',
                '--volume', '/etc/pki/tls/certs/ca-bundle.trust.crt:/etc/pki/tls/certs/ca-bundle.trust.crt:ro',
                '--volume', '/etc/pki/tls/cert.pem:/etc/pki/tls/cert.pem:ro',
                # script injection
                '--volume', '%s:%s:rw' % (sh_script, sh_script) ]

        for volume in volumes:
            if volume:
                dcmd.extend(['--volume', volume])

        dcmd.extend(['--entrypoint', sh_script])

        env = {}
        # NOTE(flaper87): Always copy the DOCKER_* environment variables as
        # they contain the access data for the docker daemon.
        for k in filter(lambda k: k.startswith('DOCKER'), os.environ.keys()):
            env[k] = os.environ.get(k)

        if os.environ.get('NET_HOST', 'false') == 'true':
            log.debug('NET_HOST enabled')
            dcmd.extend(['--net', 'host', '--volume',
                         '/etc/hosts:/etc/hosts:ro'])
        dcmd.append(config_image)
        log.debug('Running docker command: %s' % ' '.join(dcmd))

        subproc = subprocess.Popen(dcmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=env)
        cmd_stdout, cmd_stderr = subproc.communicate()
        if cmd_stdout:
            log.debug(cmd_stdout)
        if cmd_stderr:
            log.debug(cmd_stderr)
        if subproc.returncode != 0:
            log.error('Failed running docker-puppet.py for %s' % config_volume)
        else:
            # only delete successful runs, for debugging
            rm_container('docker-puppet-%s' % config_volume)
        return subproc.returncode

# Holds all the information for each process to consume.
# Instead of starting them all linearly we run them using a process
# pool.  This creates a list of arguments for the above function
# to consume.
process_map = []

for config_volume in configs:

    service = configs[config_volume]
    puppet_tags = service[1] or ''
    manifest = service[2] or ''
    config_image = service[3] or ''
    volumes = service[4] if len(service) > 4 else []

    if puppet_tags:
        puppet_tags = "file,file_line,concat,augeas,%s" % puppet_tags
    else:
        puppet_tags = "file,file_line,concat,augeas"

    process_map.append([config_volume, puppet_tags, manifest, config_image, volumes])

for p in process_map:
    log.debug('- %s' % p)

# Fire off processes to perform each configuration.  Defaults
# to the number of CPUs on the system.
p = multiprocessing.Pool(process_count)
returncodes = list(p.map(mp_puppet_config, process_map))
config_volumes = [pm[0] for pm in process_map]
success = True
for returncode, config_volume in zip(returncodes, config_volumes):
    if returncode != 0:
        log.error('ERROR configuring %s' % config_volume)
        success = False


# Update the startup configs with the config hash we generated above
config_volume_prefix = os.environ.get('CONFIG_VOLUME_PREFIX', '/var/lib/config-data')
log.debug('CONFIG_VOLUME_PREFIX: %s' % config_volume_prefix)
startup_configs = os.environ.get('STARTUP_CONFIG_PATTERN', '/var/lib/tripleo-config/docker-container-startup-config-step_*.json')
log.debug('STARTUP_CONFIG_PATTERN: %s' % startup_configs)
infiles = glob.glob('/var/lib/tripleo-config/docker-container-startup-config-step_*.json')
for infile in infiles:
    with open(infile) as f:
        infile_data = json.load(f)

    for k, v in infile_data.iteritems():
        config_volume = match_config_volume(config_volume_prefix, v)
        if config_volume:
            config_hash = get_config_hash(config_volume_prefix, config_volume)
            if config_hash:
                env = v.get('environment', [])
                env.append("TRIPLEO_CONFIG_HASH=%s" % config_hash)
                log.debug("Updating config hash for %s, config_volume=%s hash=%s" % (k, config_volume, config_hash))
                infile_data[k]['environment'] = env

    outfile = os.path.join(os.path.dirname(infile), "hashed-" + os.path.basename(infile))
    with open(outfile, 'w') as out_f:
        json.dump(infile_data, out_f)

if not success:
    sys.exit(1)
