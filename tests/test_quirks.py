#!/usr/bin/python3
# -*- Mode: Python; indent-tabs-mode: nil; tab-width: 4; coding: utf-8 -*-

import apt
import apt_pkg
import hashlib
import mock
import os
import unittest
import shutil
import tempfile

from DistUpgrade.DistUpgradeQuirks import DistUpgradeQuirks

CURDIR = os.path.dirname(os.path.abspath(__file__))


class MockController(object):
    def __init__(self):
        self._view = None


class MockConfig(object):
    pass


def make_mock_pkg(name, is_installed, candidate_rec):
    mock_pkg = mock.Mock()
    mock_pkg.name = name
    mock_pkg.is_installed = is_installed
    mock_pkg.candidate = mock.Mock()
    mock_pkg.candidate.record = candidate_rec
    return mock_pkg


class TestPatches(unittest.TestCase):

    orig_chdir = ''

    def setUp(self):
        # To patch, we need to be in the same directory as the patched files
        self.orig_chdir = os.getcwd()
        os.chdir(CURDIR)

    def tearDown(self):
        os.chdir(self.orig_chdir)

    def _verify_result_checksums(self):
        """ helper for test_patch to verify that we get the expected result """
        # simple case is foo
        patchdir = CURDIR + "/patchdir/"
        with open(patchdir + "foo") as f:
            self.assertFalse("Hello" in f.read())
        with open(patchdir + "foo_orig") as f:
            self.assertTrue("Hello" in f.read())
        md5 = hashlib.md5()
        with open(patchdir + "foo", "rb") as patch:
            md5.update(patch.read())
        self.assertEqual(md5.hexdigest(), "52f83ff6877e42f613bcd2444c22528c")
        # more complex example fstab
        md5 = hashlib.md5()
        with open(patchdir + "fstab", "rb") as patch:
            md5.update(patch.read())
        self.assertEqual(md5.hexdigest(), "c56d2d038afb651920c83106ec8dfd09")
        # most complex example
        md5 = hashlib.md5()
        with open(patchdir + "pycompile", "rb") as patch:
            md5.update(patch.read())
        self.assertEqual(md5.hexdigest(), "97c07a02e5951cf68cb3f86534f6f917")
        # with ".\n"
        md5 = hashlib.md5()
        with open(patchdir + "dotdot", "rb") as patch:
            md5.update(patch.read())
        self.assertEqual(md5.hexdigest(), "cddc4be46bedd91db15ddb9f7ddfa804")
        # test that incorrect md5sum after patching rejects the patch
        with open(patchdir + "fail") as f1, open(patchdir + "fail_orig") as f2:
            self.assertEqual(f1.read(),
                             f2.read())

    def test_patch(self):
        q = DistUpgradeQuirks(MockController(), MockConfig)
        # create patch environment
        patchdir = CURDIR + "/patchdir/"
        shutil.copy(patchdir + "foo_orig", patchdir + "foo")
        shutil.copy(patchdir + "fstab_orig", patchdir + "fstab")
        shutil.copy(patchdir + "pycompile_orig", patchdir + "pycompile")
        shutil.copy(patchdir + "dotdot_orig", patchdir + "dotdot")
        shutil.copy(patchdir + "fail_orig", patchdir + "fail")
        # apply patches
        q._applyPatches(patchdir=patchdir)
        self._verify_result_checksums()
        # now apply patches again and ensure we don't patch twice
        q._applyPatches(patchdir=patchdir)
        self._verify_result_checksums()

    def test_patch_lowlevel(self):
        # test lowlevel too
        from DistUpgrade.DistUpgradePatcher import patch, PatchError
        self.assertRaises(PatchError, patch, CURDIR + "/patchdir/fail",
                          CURDIR + "/patchdir/patchdir_fail."
                          "ed04abbc6ee688ee7908c9dbb4b9e0a2."
                          "deadbeefdeadbeefdeadbeff",
                          "deadbeefdeadbeefdeadbeff")


class TestQuirks(unittest.TestCase):

    orig_recommends = ''
    orig_status = ''

    def setUp(self):
        self.orig_recommends = apt_pkg.config.get("APT::Install-Recommends")
        self.orig_status = apt_pkg.config.get("Dir::state::status")

    def tearDown(self):
        apt_pkg.config.set("APT::Install-Recommends", self.orig_recommends)
        apt_pkg.config.set("Dir::state::status", self.orig_status)

    def test_enable_recommends_during_upgrade(self):
        controller = mock.Mock()

        config = mock.Mock()
        q = DistUpgradeQuirks(controller, config)
        # server mode
        apt_pkg.config.set("APT::Install-Recommends", "0")
        controller.serverMode = True
        self.assertFalse(apt_pkg.config.find_b("APT::Install-Recommends"))
        q.ensure_recommends_are_installed_on_desktops()
        self.assertFalse(apt_pkg.config.find_b("APT::Install-Recommends"))
        # desktop mode
        apt_pkg.config.set("APT::Install-Recommends", "0")
        controller.serverMode = False
        self.assertFalse(apt_pkg.config.find_b("APT::Install-Recommends"))
        q.ensure_recommends_are_installed_on_desktops()
        self.assertTrue(apt_pkg.config.find_b("APT::Install-Recommends"))

    def test_parse_from_modaliases_header(self):
        pkgrec = {
            "Package": "foo",
            "Modaliases": "modules1(pci:v00001002d00006700sv*sd*bc03sc*i*, "
                          "pci:v00001002d00006701sv*sd*bc03sc*i*), "
                          "module2(pci:v00001002d00006702sv*sd*bc03sc*i*, "
                          "pci:v00001001d00006702sv*sd*bc03sc*i*)"
        }
        controller = mock.Mock()
        config = mock.Mock()
        q = DistUpgradeQuirks(controller, config)
        self.assertEqual(q._parse_modaliases_from_pkg_header({}), [])
        self.assertEqual(q._parse_modaliases_from_pkg_header(pkgrec),
                         [("modules1",
                           ["pci:v00001002d00006700sv*sd*bc03sc*i*",
                            "pci:v00001002d00006701sv*sd*bc03sc*i*"]),
                          ("module2",
                           ["pci:v00001002d00006702sv*sd*bc03sc*i*",
                            "pci:v00001001d00006702sv*sd*bc03sc*i*"])])

    def disabled__as_fglrx_is_gone_testFglrx(self):
        mock_lspci_good = set(['1002:9990'])
        mock_lspci_bad = set(['8086:ac56'])
        config = mock.Mock()
        cache = apt.Cache()
        controller = mock.Mock()
        controller.cache = cache
        q = DistUpgradeQuirks(controller, config)
        if q.arch not in ['i386', 'amd64']:
            return self.skipTest("Not on an arch with fglrx package")
        self.assertTrue(q._supportInModaliases("fglrx", mock_lspci_good))
        self.assertFalse(q._supportInModaliases("fglrx", mock_lspci_bad))

    def test_screensaver_poke(self):
        # fake nothing is installed
        empty_status = tempfile.NamedTemporaryFile()
        apt_pkg.config.set("Dir::state::status", empty_status.name)

        # create quirks class
        controller = mock.Mock()
        config = mock.Mock()
        quirks = DistUpgradeQuirks(controller, config)
        quirks._pokeScreensaver()
        res = quirks._stopPokeScreensaver()
        res  # pyflakes

    def test_get_linux_metapackage(self):
        q = DistUpgradeQuirks(mock.Mock(), mock.Mock())
        mock_cache = set([
            make_mock_pkg(
                name="linux-image-3.19-24-generic",
                is_installed=True,
                candidate_rec={"Source": "linux"},
            ),
        ])
        pkgname = q._get_linux_metapackage(mock_cache, headers=False)
        self.assertEqual(pkgname, "linux-generic")

    def test_get_lpae_linux_metapackage(self):
        q = DistUpgradeQuirks(mock.Mock(), mock.Mock())
        mock_cache = set([
            make_mock_pkg(
                name="linux-image-4.2.0-16-generic-lpae",
                is_installed=True,
                candidate_rec={"Source": "linux"},
            ),
        ])
        pkgname = q._get_linux_metapackage(mock_cache, headers=False)
        self.assertEqual(pkgname, "linux-generic-lpae")

    def test_get_lowlatency_linux_metapackage(self):
        q = DistUpgradeQuirks(mock.Mock(), mock.Mock())
        mock_cache = set([
            make_mock_pkg(
                name="linux-image-4.2.0-16-lowlatency",
                is_installed=True,
                candidate_rec={"Source": "linux"},
            ),
        ])
        pkgname = q._get_linux_metapackage(mock_cache, headers=False)
        self.assertEqual(pkgname, "linux-lowlatency")

    def test_get_lts_linux_metapackage(self):
        q = DistUpgradeQuirks(mock.Mock(), mock.Mock())
        mock_cache = set([
            make_mock_pkg(
                name="linux-image-3.13.0-24-generic",
                is_installed=True,
                candidate_rec={"Source": "linux-lts-quantal"},
            ),
        ])
        pkgname = q._get_linux_metapackage(mock_cache, headers=False)
        self.assertEqual(pkgname, "linux-generic-lts-quantal")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
