#!/usr/bin/python

from __future__ import print_function

import os
import unittest

from mock import Mock

from DistUpgrade.DistUpgradeCache import MyCache
from DistUpgrade.DistUpgradeConfigParser import DistUpgradeConfig

CURDIR = os.path.dirname(os.path.abspath(__file__))


class TestKernelBaseinstaller(unittest.TestCase):

    def test_kernel_from_baseinstaller(self):
        # the upgrade expects this
        os.chdir(CURDIR + "/../DistUpgrade")
        # get a config
        config = DistUpgradeConfig(".")
        config.set("Files", "LogDir", "/tmp")
        cache = MyCache(config, None, None, lock=False)
        cache._has_kernel_headers_installed = Mock()
        cache._has_kernel_headers_installed.return_value = True
        cache.getKernelsFromBaseInstaller = Mock()
        cache.getKernelsFromBaseInstaller.return_value = \
            ["linux-generic2-pae", "linux-generic2"]
        cache.mark_install = Mock()
        cache.mark_install.return_value = True
        cache._selectKernelFromBaseInstaller()
        #print(cache.mark_install.call_args)
        calls = cache.mark_install.call_args_list
        self.assertEqual(len(calls), 2)
        cache.mark_install.assert_any_call(
            "linux-generic2-pae", "Selecting new kernel from base-installer")
        cache.mark_install.assert_any_call(
            "linux-headers-generic2-pae",
            "Selecting new kernel headers from base-installer")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
