#
# Copyright 2018 Red Hat Inc.
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

from unittest import mock

import contextlib
import six
import stat
import sys

from oslotest import base


class FakeSelinux(object):
    @staticmethod
    def lgetfilecon(path):
        pass

    @staticmethod
    def lsetfilecon(path, context):
        pass
sys.modules["selinux"] = FakeSelinux

from container_config_scripts.nova_statedir_ownership import \
    NovaStatedirOwnershipManager  # noqa: E402
from container_config_scripts.nova_statedir_ownership import PathManager  # noqa: E402

# Real chown would require root, so in order to test this we need to fake
# all of the methods that interact with the filesystem

current_uid = 100
current_gid = 100


class FakeStatInfo(object):
    def __init__(self, st_mode, st_uid, st_gid):
        self.st_mode = st_mode
        self.st_uid = st_uid
        self.st_gid = st_gid

    def get_ids(self):
        return (self.st_uid, self.st_gid)


def generate_testtree1(nova_uid, nova_gid):
    return {
        '/var/lib/nova': {
            'stat': FakeStatInfo(st_mode=stat.S_IFDIR,
                                 st_uid=nova_uid,
                                 st_gid=nova_gid),
            'nfs': False,
        },
        '/var/lib/_nova_secontext': {
            'stat': FakeStatInfo(st_mode=stat.S_IFDIR,
                                 st_uid=nova_uid,
                                 st_gid=nova_gid),
            'nfs': False,
        },

        '/var/lib/nova/instances': {
            'stat': FakeStatInfo(st_mode=stat.S_IFDIR,
                         st_uid=nova_uid,
                         st_gid=nova_gid),
            'nfs': False,
        },
        '/var/lib/nova/instances/foo': {
            'stat': FakeStatInfo(st_mode=stat.S_IFDIR,
                                 st_uid=nova_uid,
                                 st_gid=nova_gid),
            'nfs': True,
        },
        '/var/lib/nova/instances/foo/bar': {
            'stat': FakeStatInfo(st_mode=stat.S_IFREG,
                                 st_uid=0,
                                 st_gid=0),
            'nfs': True,
        },
        '/var/lib/nova/instances/foo/baz': {
            'stat': FakeStatInfo(st_mode=stat.S_IFREG,
                                 st_uid=nova_uid,
                                 st_gid=nova_gid),
            'nfs': True,
        },
        '/var/lib/nova/instances/foo/abc': {
            'stat': FakeStatInfo(st_mode=stat.S_IFREG,
                                 st_uid=0,
                                 st_gid=nova_gid),
            'nfs': True,
        },
        '/var/lib/nova/instances/foo/def': {
            'stat': FakeStatInfo(st_mode=stat.S_IFREG,
                                 st_uid=nova_uid,
                                 st_gid=0),
            'nfs': True,
        },
    }


def generate_testtree2(marker_uid, marker_gid, *args, **kwargs):
    tree = generate_testtree1(*args, **kwargs)
    tree.update({
        '/var/lib/nova/upgrade_marker': {
            'stat': FakeStatInfo(st_mode=stat.S_IFREG,
                                 st_uid=marker_uid,
                                 st_gid=marker_gid),
            'nfs': False,
        }
    })
    return tree


def generate_fake_stat(testtree):
    def fake_stat(path):
        return testtree.get(path, {}).get('stat')
    return fake_stat


def generate_fake_chown(testtree):
    def fake_chown(path, uid, gid):
        if uid != -1:
            testtree[path]['stat'].st_uid = uid
        if gid != -1:
            testtree[path]['stat'].st_gid = gid
    return fake_chown


def generate_fake_exists(testtree):
    def fake_exists(path):
        return path in testtree
    return fake_exists


def generate_fake_listdir(testtree):
    def fake_listdir(path):
        path_parts = path.split('/')
        for entry in testtree:
            entry_parts = entry.split('/')
            if (entry_parts[:len(path_parts)] == path_parts and
                    len(entry_parts) == len(path_parts) + 1):
                yield entry
    return fake_listdir


def generate_fake_unlink(testtree):
    def fake_unlink(path):
        del testtree[path]
    return fake_unlink


def generate_fake_lsetfilecon(testtree):
    def fake_lsetfilecon(path, context):
        if testtree[path]['nfs']:
            e = OSError('Operation not supported')
            e.errno = 95
            raise e


@contextlib.contextmanager
def fake_testtree(testtree):
    fake_stat = generate_fake_stat(testtree)
    fake_chown = generate_fake_chown(testtree)
    fake_exists = generate_fake_exists(testtree)
    fake_listdir = generate_fake_listdir(testtree)
    fake_unlink = generate_fake_unlink(testtree)
    fake_lsetfilecon = generate_fake_lsetfilecon(testtree)
    with mock.patch('os.chown',
                    side_effect=fake_chown) as fake_chown:
        with mock.patch('os.path.exists',
                        side_effect=fake_exists) as fake_exists:
            with mock.patch('os.listdir',
                            side_effect=fake_listdir) as fake_listdir:
                with mock.patch('pwd.getpwnam',
                                return_value=(0, 0, current_uid, current_gid)):
                    with mock.patch('os.stat',
                                    side_effect=fake_stat) as fake_stat:
                        with mock.patch(
                                'os.unlink',
                                side_effect=fake_unlink
                                ) as fake_unlink:
                            with mock.patch(
                                    'selinux.lgetfilecon',
                                    return_value=[10, 'newcontext'],
                                    ) as fake_lgetfilecon:
                                with mock.patch(
                                        'selinux.lsetfilecon',
                                        side_effect=fake_lsetfilecon,
                                        ) as fake_lsetfilecon:
                                    yield (fake_chown,
                                           fake_exists,
                                           fake_listdir,
                                           fake_stat,
                                           fake_unlink,
                                           fake_lgetfilecon,
                                           fake_lsetfilecon)


def assert_ids(testtree, path, uid, gid):
    statinfo = testtree[path]['stat']
    assert (uid, gid) == (statinfo.st_uid, statinfo.st_gid), \
        "{}: expected ownership {}:{} actual {}:{}".format(
            path, uid, gid, statinfo.st_uid, statinfo.st_gid
        )


class PathManagerCase(base.BaseTestCase):
    def test_file(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree):
            pathinfo = PathManager('/var/lib/nova/instances/foo/baz')
            self.assertTrue(pathinfo.has_owner(current_uid, current_gid))
            self.assertTrue(pathinfo.has_either(current_uid, 0))
            self.assertTrue(pathinfo.has_either(0, current_gid))
            self.assertFalse(pathinfo.is_dir)
            self.assertEqual(str(pathinfo), 'uid: {} gid: {} path: {}'.format(
                current_uid, current_gid, '/var/lib/nova/instances/foo/baz'
            ))

    def test_dir(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree):
            pathinfo = PathManager('/var/lib/nova')
            self.assertTrue(pathinfo.has_owner(current_uid, current_gid))
            self.assertTrue(pathinfo.has_either(current_uid, 0))
            self.assertTrue(pathinfo.has_either(0, current_gid))
            self.assertTrue(pathinfo.is_dir)
            self.assertEqual(str(pathinfo), 'uid: {} gid: {} path: {}'.format(
                current_uid, current_gid, '/var/lib/nova/'
            ))

    def test_chown(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree):
            pathinfo = PathManager('/var/lib/nova/instances/foo/baz')
            self.assertTrue(pathinfo.has_owner(current_uid, current_gid))
            pathinfo.chown(current_uid + 1, current_gid)
            assert_ids(testtree, pathinfo.path, current_uid + 1, current_gid)

    def test_chgrp(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree):
            pathinfo = PathManager('/var/lib/nova/instances/foo/baz')
            self.assertTrue(pathinfo.has_owner(current_uid, current_gid))
            pathinfo.chown(current_uid, current_gid + 1)
            assert_ids(testtree, pathinfo.path, current_uid, current_gid + 1)

    def test_chown_chgrp(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree):
            pathinfo = PathManager('/var/lib/nova/instances/foo/baz')
            self.assertTrue(pathinfo.has_owner(current_uid, current_gid))
            pathinfo.chown(current_uid + 1, current_gid + 1)
            assert_ids(testtree, pathinfo.path,
                       current_uid + 1, current_gid + 1)


class NovaStatedirOwnershipManagerTestCase(base.BaseTestCase):
    def test_no_upgrade_marker(self):
        testtree = generate_testtree1(current_uid, current_gid)

        with fake_testtree(testtree) as (fake_chown, _, _, _, _, _, fake_lsetfilecon):
            NovaStatedirOwnershipManager('/var/lib/nova').run()
            fake_chown.assert_not_called()
            fake_lsetfilecon.assert_any_call('/var/lib/nova', 'newcontext')
            fake_lsetfilecon.assert_any_call('/var/lib/nova/instances/foo', 'newcontext')
            chcon_paths = [x[0][0] for x in fake_lsetfilecon.call_args_list]
            self.assertNotIn('/var/lib/nova/instances/foo/bar', chcon_paths)

    def test_upgrade_marker_no_id_change(self):
        testtree = generate_testtree2(current_uid,
                                      current_gid,
                                      current_uid,
                                      current_gid)

        with fake_testtree(testtree) as (fake_chown, _, _, _, fake_unlink, _, _):
            NovaStatedirOwnershipManager('/var/lib/nova').run()
            fake_chown.assert_not_called()
            fake_unlink.assert_called_with('/var/lib/nova/upgrade_marker')

    def test_upgrade_marker_id_change(self):
        other_uid = current_uid + 1
        other_gid = current_gid + 1
        testtree = generate_testtree2(other_uid,
                                      other_gid,
                                      other_uid,
                                      other_gid)

        # Determine which paths should change uid/gid
        expected_changes = {}
        for k, v in six.iteritems(testtree):
            if k == '/var/lib/nova/upgrade_marker':
                # Ignore the marker, it should be deleted
                continue
            if k == '/var/lib/_nova_secontext':
                # Ignore, outside tree
                continue
            v = v['stat']
            if v.st_uid == other_uid or v.st_gid == other_gid:
                expected_changes[k] = (
                    current_uid if v.st_uid == other_uid else v.st_uid,
                    current_gid if v.st_gid == other_gid else v.st_gid
                )

        with fake_testtree(testtree) as (_, _, _, _, fake_unlink, _, _):
            NovaStatedirOwnershipManager('/var/lib/nova').run()
            for fn, expected in six.iteritems(expected_changes):
                assert_ids(testtree, fn, expected[0], expected[1])
            fake_unlink.assert_called_with('/var/lib/nova/upgrade_marker')
