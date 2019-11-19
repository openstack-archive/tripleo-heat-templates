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

# Shell script tool to run puppet inside of the given container image.
# Uses the config file at /var/lib/container-puppet/container-puppet.json
# as a source for a JSON array of
# [config_volume, puppet_tags, manifest, config_image, [volumes]] settings
# that can be used to generate config files or run ad-hoc puppet modules
# inside of a container.

import glob
import json
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time

from paunch import runner as containers_runner


def get_logger():
    """Return a logger object."""
    logger = logging.getLogger()
    ch = logging.StreamHandler(sys.stdout)
    if os.environ.get('DEBUG') in ['True', 'true']:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(process)s -- %(message)s'
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def local_subprocess_call(cmd, env=None):
    """General run method for subprocess calls.

    :param cmd: list
    returns: tuple
    """
    subproc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env
    )
    stdout, stderr = subproc.communicate()
    return stdout, stderr, subproc.returncode


def pull_image(name):
    _, _, rc = local_subprocess_call(cmd=[CLI_CMD, 'inspect', name])
    if rc == 0:
        LOG.info('Image already exists: %s' % name)
        return

    retval = -1
    count = 0
    LOG.info('Pulling image: %s' % name)
    while retval != 0:
        count += 1
        stdout, stderr, retval = local_subprocess_call(
            cmd=[CLI_CMD, 'pull', name]
        )
        if retval != 0:
            time.sleep(3)
            LOG.warning('%s pull failed: %s' % (CONTAINER_CLI, stderr))
            LOG.warning('retrying pulling image: %s' % name)
        if count >= 5:
            LOG.error('Failed to pull image: %s' % name)
            break
    if stdout:
        LOG.debug(stdout)
    if stderr:
        LOG.debug(stderr)


def match_config_volumes(prefix, config):
    # Match the mounted config volumes - we can't just use the
    # key as e.g "novacomute" consumes config-data/nova
    try:
        volumes = config.get('volumes', [])
    except AttributeError:
        LOG.error(
            'Error fetching volumes. Prefix: %s - Config: %s' % (
                prefix,
                config
            )
        )
        raise
    return sorted([os.path.dirname(v.split(":")[0]) for v in volumes if
                   v.startswith(prefix)])


def get_config_hash(config_volume):
    hashfile = "%s.md5sum" % config_volume
    LOG.debug(
        "Looking for hashfile %s for config_volume %s" % (
            hashfile,
            config_volume
        )
    )
    hash_data = None
    if os.path.isfile(hashfile):
        LOG.debug(
            "Got hashfile %s for config_volume %s" % (
                hashfile,
                config_volume
            )
        )
        with open(hashfile) as f:
            hash_data = f.read().rstrip()
    return hash_data


def rm_container(name):
    if os.environ.get('SHOW_DIFF', None):
        LOG.info('Diffing container: %s' % name)
        stdout, stderr, retval = local_subprocess_call(
            cmd=[CLI_CMD, 'diff', name]
        )
        if stdout:
            LOG.debug(stdout)
        if stderr:
            LOG.debug(stderr)

    def rm_process_call(rm_cli_cmd):
        stdout, stderr, retval = local_subprocess_call(
            cmd=rm_cli_cmd)
        if stdout:
            LOG.debug(stdout)
        if stderr and 'Error response from daemon' in stderr:
            LOG.debug(stderr)

    LOG.info('Removing container: %s' % name)
    rm_cli_cmd = [CLI_CMD, 'rm']
    rm_cli_cmd.append(name)
    rm_process_call(rm_cli_cmd)
    # --storage is used as a mitigation of
    # https://github.com/containers/libpod/issues/3906
    # Also look https://bugzilla.redhat.com/show_bug.cgi?id=1747885
    if CONTAINER_CLI == 'podman':
        rm_storage_cli_cmd = [CLI_CMD, 'rm', '--storage']
        rm_storage_cli_cmd.append(name)
        rm_process_call(rm_storage_cli_cmd)


def mp_puppet_config(*args):
    (
        config_volume,
        puppet_tags,
        manifest,
        config_image,
        volumes,
        privileged,
        check_mode,
        keep_container
    ) = args[0]
    LOG.info('Starting configuration of %s using image %s' %
             (config_volume, config_image))
    LOG.debug('config_volume %s' % config_volume)
    LOG.debug('puppet_tags %s' % puppet_tags)
    LOG.debug('manifest %s' % manifest)
    LOG.debug('config_image %s' % config_image)
    LOG.debug('volumes %s' % volumes)
    LOG.debug('privileged %s' % privileged)
    LOG.debug('check_mode %s' % check_mode)
    LOG.debug('keep_container %s' % keep_container)

    with tempfile.NamedTemporaryFile() as tmp_man:
        with open(tmp_man.name, 'w') as man_file:
            man_file.write('include ::tripleo::packages\n')
            man_file.write(manifest)

        uname = RUNNER.unique_container_name(
            'container-puppet-%s' % config_volume
        )
        rm_container(uname)
        pull_image(config_image)

        common_dcmd = [
            CLI_CMD,
            'run',
            '--user',
            'root',
            '--name',
            uname,
            '--env',
            'PUPPET_TAGS=%s' % puppet_tags,
            '--env',
            'NAME=%s' % config_volume,
            '--env',
            'HOSTNAME=%s' % os.environ.get('SHORT_HOSTNAME'),
            '--env',
            'NO_ARCHIVE=%s' % os.environ.get('NO_ARCHIVE', ''),
            '--env',
            'STEP=%s' % os.environ.get('STEP', '6'),
            '--env',
            'NET_HOST=%s' % os.environ.get('NET_HOST', 'false'),
            '--env',
            'DEBUG=%s' % os.environ.get('DEBUG', 'false'),
            '--volume',
            '/etc/localtime:/etc/localtime:ro',
            '--volume',
            '%s:/etc/config.pp:ro' % tmp_man.name,
            '--volume',
            '/etc/puppet/:/tmp/puppet-etc/:ro',
            # OpenSSL trusted CA injection
            '--volume',
            '/etc/pki/ca-trust/extracted:/etc/pki/ca-trust/extracted:ro',
            '--volume',
            '/etc/pki/tls/certs/ca-bundle.crt:'
            '/etc/pki/tls/certs/ca-bundle.crt:ro',
            '--volume',
            '/etc/pki/tls/certs/ca-bundle.trust.crt:'
            '/etc/pki/tls/certs/ca-bundle.trust.crt:ro',
            '--volume',
            '/etc/pki/tls/cert.pem:/etc/pki/tls/cert.pem:ro',
            '--volume',
            '%s:/var/lib/config-data/:rw' % CONFIG_VOLUME_PREFIX,
            # facter caching
            '--volume',
            '/var/lib/container-puppet/puppetlabs/facter.conf:'
            '/etc/puppetlabs/facter/facter.conf:ro',
            '--volume',
            '/var/lib/container-puppet/puppetlabs/:/opt/puppetlabs/:ro',
            # Syslog socket for puppet logs
            '--volume', '/dev/log:/dev/log:rw'
        ]

        # Remove container by default after the run
        # This should mitigate the "ghost container" issue described here
        # https://bugzilla.redhat.com/show_bug.cgi?id=1747885
        # https://bugs.launchpad.net/tripleo/+bug/1840691
        if not keep_container:
            common_dcmd.append('--rm')

        if privileged:
            common_dcmd.append('--privileged')

        if CONTAINER_CLI == 'podman':
            log_path = os.path.join(CONTAINER_LOG_STDOUT_PATH, uname)
            logging = ['--log-driver', 'k8s-file',
                       '--log-opt',
                       'path=%s.log' % log_path]
            common_dcmd.extend(logging)
        elif CONTAINER_CLI == 'docker':
            # NOTE(flaper87): Always copy the DOCKER_* environment variables as
            # they contain the access data for the docker daemon.
            for k in os.environ.keys():
                if k.startswith('DOCKER'):
                    ENV[k] = os.environ.get(k)

        common_dcmd += CLI_DCMD

        if CHECK_MODE:
            common_dcmd.extend([
                '--volume',
                '/etc/puppet/check-mode:/tmp/puppet-check-mode:ro'])

        for volume in volumes:
            if volume:
                common_dcmd.extend(['--volume', volume])

        common_dcmd.extend(['--entrypoint', SH_SCRIPT])

        if os.environ.get('NET_HOST', 'false') == 'true':
            LOG.debug('NET_HOST enabled')
            common_dcmd.extend(['--net', 'host', '--volume',
                                '/etc/hosts:/etc/hosts:ro'])
        else:
            LOG.debug('running without containers Networking')
            common_dcmd.extend(['--net', 'none'])

        # script injection as the last mount to make sure it's accessible
        # https://github.com/containers/libpod/issues/1844
        common_dcmd.extend(['--volume', '%s:%s:ro' % (SH_SCRIPT, SH_SCRIPT)])

        common_dcmd.append(config_image)

        # https://github.com/containers/libpod/issues/1844
        # This block will run "CONTAINER_CLI" run 5 times before to fail.
        retval = -1
        count = 0
        LOG.debug(
            'Running %s command: %s' % (
                CONTAINER_CLI,
                ' '.join(common_dcmd)
            )
        )
        while count < 3:
            count += 1
            stdout, stderr, retval = local_subprocess_call(
                cmd=common_dcmd,
                env=ENV
            )
            # puppet with --detailed-exitcodes will return 0 for success and
            # no changes and 2 for success and resource changes. Other
            # numbers are failures
            if retval in [0, 2]:
                if stdout:
                    LOG.debug('%s run succeeded: %s' % (common_dcmd, stdout))
                if stderr:
                    LOG.warning(stderr)
                # only delete successful runs, for debugging
                rm_container(uname)
                break
            time.sleep(3)
            LOG.error(
                '%s run failed after %s attempt(s): %s' % (
                    common_dcmd,
                    stderr,
                    count
                )
            )
            LOG.warning('Retrying running container: %s' % config_volume)
        else:
            if stdout:
                LOG.debug(stdout)
            if stderr:
                LOG.debug(stderr)
            LOG.error('Failed running container for %s' % config_volume)
        LOG.info(
            'Finished processing puppet configs for %s' % (
                config_volume
            )
        )
        return retval


def infile_processing(infiles):
    for infile in infiles:
        # If the JSON is already hashed, we'll skip it; and a new hashed file will
        # be created if config changed.
        if 'hashed' in infile:
            LOG.debug('%s skipped, already hashed' % infile)
            continue

        with open(infile) as f:
            infile_data = json.load(f)

        # if the contents of the file is None, we need should just create an empty
        # data set see LP#1828295
        if not infile_data:
            infile_data = {}

        c_name = os.path.splitext(os.path.basename(infile))[0]
        config_volumes = match_config_volumes(
            CONFIG_VOLUME_PREFIX,
            infile_data
        )
        config_hashes = [
            get_config_hash(volume_path) for volume_path in config_volumes
        ]
        config_hashes = filter(None, config_hashes)
        config_hash = '-'.join(config_hashes)
        if config_hash:
            LOG.debug(
                "Updating config hash for %s, config_volume=%s hash=%s" % (
                    c_name,
                    config_volume,
                    config_hash
                )
            )
            # When python 27 support is removed, we will be able to use:
            #   z = {**x, **y} to merge the dicts.
            if infile_data.get('environment', None) is None:
                infile_data['environment'] = {}
            infile_data['environment'].update(
                {'TRIPLEO_CONFIG_HASH': config_hash}
            )

        outfile = os.path.join(
            os.path.dirname(
                infile
            ), "hashed-" + os.path.basename(infile)
        )
        with open(outfile, 'w') as out_f:
            os.chmod(out_f.name, 0o600)
            json.dump(infile_data, out_f, indent=2)


if __name__ == '__main__':
    PUPPETS = (
        '/usr/share/openstack-puppet/modules/:'
        '/usr/share/openstack-puppet/modules/:ro'
    )
    SH_SCRIPT = '/var/lib/container-puppet/container-puppet.sh'
    CONTAINER_CLI = os.environ.get('CONTAINER_CLI', 'podman')
    CONTAINER_LOG_STDOUT_PATH = os.environ.get(
        'CONTAINER_LOG_STDOUT_PATH',
        '/var/log/containers/stdouts'
    )
    CLI_CMD = '/usr/bin/' + CONTAINER_CLI
    LOG = get_logger()
    LOG.info('Running container-puppet')
    CONFIG_VOLUME_PREFIX = os.path.abspath(
        os.environ.get(
            'CONFIG_VOLUME_PREFIX',
            '/var/lib/config-data'
        )
    )
    CHECK_MODE = int(os.environ.get('CHECK_MODE', 0))
    LOG.debug('CHECK_MODE: %s' % CHECK_MODE)
    if CONTAINER_CLI == 'docker':
        CLI_DCMD = ['--volume', PUPPETS]
        ENV = {}
        RUNNER = containers_runner.DockerRunner(
            'container-puppet',
            cont_cmd='docker',
            log=LOG
        )
    elif CONTAINER_CLI == 'podman':
        # podman doesn't allow relabeling content in /usr and
        # doesn't support named volumes
        CLI_DCMD = [
            '--security-opt',
            'label=disable',
            '--volume',
            PUPPETS
        ]
        # podman need to find dependent binaries that are in environment
        ENV = {'PATH': os.environ['PATH']}
        RUNNER = containers_runner.PodmanRunner(
            'container-puppet',
            cont_cmd='podman',
            log=LOG
        )
    else:
        LOG.error('Invalid CONTAINER_CLI: %s' % CONTAINER_CLI)
        raise SystemExit()

    config_file = os.environ.get(
        'CONFIG',
        '/var/lib/container-puppet/container-puppet.json'
    )
    LOG.debug('CONFIG: %s' % config_file)
    # If specified, only this config_volume will be used
    CONFIG_VOLUME_ONLY = os.environ.get('CONFIG_VOLUME', None)
    with open(config_file) as f:
        JSON_DATA = json.load(f)

    # To save time we support configuring 'shared' services at the same
    # time. For example configuring all of the heat services
    # in a single container pass makes sense and will save some time.
    # To support this we merge shared settings together here.
    #
    # We key off of config_volume as this should be the same for a
    # given group of services.  We are also now specifying the container
    # in which the services should be configured.  This should match
    # in all instances where the volume name is also the same.
    CONFIGS = {}
    for service in (JSON_DATA or []):
        if service is None:
            continue
        if isinstance(service, dict):
            service = [
                service.get('config_volume'),
                service.get('puppet_tags'),
                service.get('step_config'),
                service.get('config_image'),
                service.get('volumes', []),
                service.get('privileged', False),
            ]

        CONFIG_VOLUME = service[0] or ''
        PUPPET_TAGS = service[1] or ''
        MANIFEST = service[2] or ''
        CONFIG_IMAGE = service[3] or ''
        VOLUMES = service[4] if len(service) > 4 else []

        if not MANIFEST or not CONFIG_IMAGE:
            continue

        LOG.debug('config_volume %s' % CONFIG_VOLUME)
        LOG.debug('puppet_tags %s' % PUPPET_TAGS)
        LOG.debug('manifest %s' % MANIFEST)
        LOG.debug('config_image %s' % CONFIG_IMAGE)
        LOG.debug('volumes %s' % VOLUMES)
        LOG.debug('privileged %s' % service[5] if len(service) > 5 else False)
        # We key off of config volume for all configs.
        if CONFIG_VOLUME in CONFIGS:
            # Append puppet tags and manifest.
            LOG.debug("Existing service, appending puppet tags and manifest")
            if PUPPET_TAGS:
                CONFIGS[CONFIG_VOLUME][1] = '%s,%s' % (
                    CONFIGS[CONFIG_VOLUME][1],
                    PUPPET_TAGS
                )
            if MANIFEST:
                CONFIGS[CONFIG_VOLUME][2] = '%s\n%s' % (
                    CONFIGS[CONFIG_VOLUME][2],
                    MANIFEST
                )
            if CONFIGS[CONFIG_VOLUME][3] != CONFIG_IMAGE:
                LOG.warning("Config containers do not match even though"
                            " shared volumes are the same!")
            if VOLUMES:
                CONFIGS[CONFIG_VOLUME][4].extend(VOLUMES)

        else:
            if not CONFIG_VOLUME_ONLY or (CONFIG_VOLUME_ONLY == CONFIG_VOLUME):
                LOG.debug("Adding new service")
                CONFIGS[CONFIG_VOLUME] = service
            else:
                LOG.debug(
                    "Ignoring %s due to $CONFIG_VOLUME=%s" % (
                        CONFIG_VOLUME,
                        CONFIG_VOLUME_ONLY
                    )
                )

    LOG.info('Service compilation completed.')

    # Holds all the information for each process to consume.
    # Instead of starting them all linearly we run them using a process
    # pool.  This creates a list of arguments for the above function
    # to consume.
    PROCESS_MAP = []
    for config_volume in CONFIGS:

        SERVICE = CONFIGS[config_volume]
        PUPPET_TAGS = SERVICE[1] or ''

        if PUPPET_TAGS:
            PUPPET_TAGS = "file,file_line,concat,augeas,cron,%s" % PUPPET_TAGS
        else:
            PUPPET_TAGS = "file,file_line,concat,augeas,cron"

        PROCESS_ITEM = [
            config_volume,
            PUPPET_TAGS,
            SERVICE[2] or '',
            SERVICE[3] or '',
            SERVICE[4] if len(SERVICE) > 4 else [],
            SERVICE[5] if len(SERVICE) > 5 else False,
            CHECK_MODE,
            SERVICE[6] if len(SERVICE) > 6 else False
        ]
        PROCESS_MAP.append(PROCESS_ITEM)
        LOG.debug('- %s' % PROCESS_ITEM)

    # Fire off processes to perform each configuration.  Defaults
    # to the number of CPUs on the system.
    PROCESS = multiprocessing.Pool(int(os.environ.get('PROCESS_COUNT', 2)))
    RETURNCODES = list(PROCESS.map(mp_puppet_config, PROCESS_MAP))
    CONFIG_VOLUMES = [pm[0] for pm in PROCESS_MAP]
    SUCCESS = True
    for returncode, config_volume in zip(RETURNCODES, CONFIG_VOLUMES):
        if returncode not in [0, 2]:
            LOG.error('ERROR configuring %s' % config_volume)
            SUCCESS = False

    # Update the startup configs with the config hash we generated above
    STARTUP_CONFIGS = os.environ.get(
        'STARTUP_CONFIG_PATTERN',
        '/var/lib/tripleo-config/docker-container-startup-config-step_*.json'
    )
    LOG.debug('STARTUP_CONFIG_PATTERN: %s' % STARTUP_CONFIGS)
    # Run infile processing
    infile_processing(infiles=glob.glob(STARTUP_CONFIGS))

    if not SUCCESS:
        raise SystemExit()
