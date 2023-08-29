#!/usr/bin/env python3
#
# Copyright 2022 Red Hat Inc.
#
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
import os
import shutil
import subprocess
import sys

from pkg_resources import packaging


SOCKET = "unix:/run/podman/podman.sock"
BASE_FORMAT = "{service: .Name, container: .Id, status: .State.Running, "
SKIP_LIST = ['_bootstrap', 'container-puppet-', '_db_sync',
             '_ensure_', '_fix_', '_init_', '_map_', '_wait_',
             'mysql_data_ownership', 'configure_cms_options']


def execute(cmd, workdir: str = None,
            prev_proc: subprocess.Popen = None) -> subprocess.Popen:
    # Note(mmagr): When this script is executed by collectd-sensubility started
    #              via collectd the script has non-root permission but inherits
    #              environment from collectd with root permission. We need
    #              to avoid sensubility access /root when using podman-remote.
    #              See https://bugzilla.redhat.com/show_bug.cgi?id=2091076 for
    #              more info.
    proc_env = os.environ.copy()
    proc_env["HOME"] = "/tmp"
    if type(cmd[0]) is list:  # multiple piped commands
        last = prev_proc
        for c in cmd:
            last = execute(c, workdir, last)
        return last
    else:  # single command
        inpipe = prev_proc.stdout if prev_proc is not None else None
        proc = subprocess.Popen(cmd, cwd=workdir, env=proc_env, stdin=inpipe,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if prev_proc is not None:
            prev_proc.stdout.close()
            prev_proc.stderr.close()
        return proc


def fetch_container_health(containers):
    proc = execute([shutil.which('podman-remote'),
                    '--url', SOCKET, 'version',
                    '--format', r'{{.Server.Version}}'])
    o, e = proc.communicate()
    try:
        if packaging.version.parse(o.decode().strip()) >= packaging.version.parse("4.0.0"):
            fmt = BASE_FORMAT + "healthy: .State.Health.Status}"
        else:
            fmt = BASE_FORMAT + "healthy: .State.Healthcheck.Status}"
    except Exception:
        # keep podman-4.0.0+ format in case of version decoding error
        fmt = BASE_FORMAT + "healthy: .State.Health.Status}"

    out = []
    for cont in set(containers.split('\n')) - set(SKIP_LIST):
        if not cont:
            continue
        proc = execute([
            [shutil.which('podman-remote'),
                '--url', SOCKET, 'inspect', cont],
            [shutil.which('jq'), '.[] | %s' % fmt]
        ])
        o, e = proc.communicate()
        if proc.returncode != 0:
            msg = "Failed to fetch status of %s: %s" % (cont, e.decode())
            return proc.returncode, msg

        item = json.loads(o.decode())
        item['status'] = 'running' if item['status'] else 'stopped'
        if len(item['healthy']) > 0 and item['status'] != 'stopped':
            item['status'] = item['healthy']

        healthy = item['status'] in ('healthy', 'running')
        item['healthy'] = int(healthy)
        out.append(item)
    return 0, out


if __name__ == "__main__":
    proc = execute([shutil.which('podman-remote'), '--url', SOCKET,
                    'ps', '--all', '--format', '{{.Names}}'])
    o, e = proc.communicate()
    if proc.returncode != 0:
        print("Failed to list containers:\n%s\n%s" % (o.decode(), e.decode()))
        sys.exit(1)

    rc, status = fetch_container_health(o.decode())
    if rc != 0:
        print("Failed to inspect containers:\n%s" % status)
        sys.exit(rc)
    print(json.dumps(status))
