#!/usr/bin/python


import logging
import glob
import sys
import unittest

sys.path.insert(0, "../")
from UpdateManager.Core.utils import (is_child_of_process_name, 
                                      estimate_kernel_size_in_boot)

class TestUtils(unittest.TestCase):

    def test_estimate_kernel_size(self):
        estimate = estimate_kernel_size_in_boot()
        self.assertTrue(estimate > 0)

    def test_is_child_of_process_name(self):
        self.assertTrue(is_child_of_process_name("init"))
        self.assertFalse(is_child_of_process_name("mvo"))
        for e in glob.glob("/proc/[0-9]*"):
            pid = int(e[6:])
            is_child_of_process_name("gdm", pid)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == "-v":
        logging.basicConfig(level=logging.DEBUG)
    unittest.main()
    
