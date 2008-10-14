#!/usr/bin/python

import unittest
import tempfile
import shutil
import sys
import os
import os.path
import apt_pkg
import tempfile
sys.path.insert(0,"../DistUpgrade")

from DistUpgradeAptCdrom import AptCdrom


class testAptCdrom(unittest.TestCase):
    " this test the apt-cdrom implementation "
    
#    def testAdd(self):
#        p = "./test-data-cdrom"
#        apt_pkg.Config.Set("Dir::State::lists","/tmp")
#        cdrom = AptCdrom(None, p)
#        self.assert_(cdrom._doAdd())

    def testWriteDatabase(self):
        expect =  """CD::36e3f69081b7d10081d167b137886a71-2 "Ubuntu 8.10 _Intrepid Ibex_ - Beta amd64 (20080930.4)";
CD::36e3f69081b7d10081d167b137886a71-2::Label "Ubuntu 8.10 _Intrepid Ibex_ - Beta amd64 (20080930.4)";
"""
        p = "./test-data-cdrom"
        database="./test-data-cdrom/cdrom.list"
        apt_pkg.Config.Set("Dir::State::cdroms", database)
        os.unlink(database)
        cdrom = AptCdrom(None, p)
        cdrom._writeDatabase()
        self.assert_(open(database).read() == expect)
    
    def testScanCD(self):
        p = "./test-data-cdrom"
        cdrom = AptCdrom(None, p)
        (p,s,i18n) = cdrom._scanCD()
        self.assert_(len(p) > 0 and len(s) > 0 and len(i18n) > 0,
                     "failed to scan packages files (%s) (%s)" % (p,s))
        #print p,s,i18n
    
    def testDropArch(self):
        p = "./test-data-cdrom"
        cdrom = AptCdrom(None, p)
        (p,s,i18n) = cdrom._scanCD()
        self.assert_(len(cdrom._dropArch(p)) < len(p),
                     "drop arch did not drop (%s) < (%s)" % (len(cdrom._dropArch(p)), len(p)))

    def testDiskName(self):
        " read and escape the disskname"
        cdrom = AptCdrom(None, "./test-data-cdrom")
        s = cdrom._readDiskName()
        self.assert_(s == "Ubuntu 8.10 _Intrepid Ibex_ - Beta amd64 (20080930.4)",
                     "_readDiskName failed (got %s)" % s)

    def testGenerateSourcesListLine(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        p = cdrom._dropArch(p)
        line = cdrom._generateSourcesListLine(cdrom._readDiskName(), p)
        #print line
        self.assert_(line == "deb cdrom:[Ubuntu 8.10 _Intrepid Ibex_ - Beta amd64 (20080930.4)]/ intrepid main restricted",
                     "deb line wrong (got %s)" % line)

    def testCopyi18n(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        p = cdrom._dropArch(p)
        d=tempfile.mkdtemp()
        cdrom._copyTranslations(i18n, d)
        self.assert_(os.path.exists(os.path.join(d,"Ubuntu%208.10%20%5fIntrepid%20Ibex%5f%20-%20Beta%20amd64%20(20080930.4)_dists_intrepid_main_i18n_Translation-be")),
                                                 "no outfile in '%s'" % os.listdir(d))

    def testCopyPackages(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        p = cdrom._dropArch(p)
        d=tempfile.mkdtemp()
        cdrom._copyPackages(p, d)
        self.assert_(os.path.exists(os.path.join(d,"Ubuntu%208.10%20%5fIntrepid%20Ibex%5f%20-%20Beta%20amd64%20(20080930.4)_dists_intrepid_main_binary-amd64_Packages")),
                                                 "no outfile in '%s'" % os.listdir(d))

    def testVerifyRelease(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        res=cdrom._verifyRelease(s)
        self.assert_(res==True)

    def testCopyRelease(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        d=tempfile.mkdtemp()
        cdrom._copyRelease(s, d)
        self.assert_(os.path.exists(os.path.join(d,"Ubuntu%208.10%20%5fIntrepid%20Ibex%5f%20-%20Beta%20amd64%20(20080930.4)_dists_intrepid_Release")),
                     "no outfile in '%s' (%s)" % (d, os.listdir(d)))
        

    def testSourcesList(self):
        cdrom = AptCdrom(None, "./test-data-cdrom")
        (p,s,i18n) = cdrom._scanCD()
        p=cdrom._dropArch(p)
        line=cdrom._generateSourcesListLine(cdrom._readDiskName(), p)
        self.assert_(line == "deb cdrom:[Ubuntu 8.10 _Intrepid Ibex_ - Beta amd64 (20080930.4)]/ intrepid main restricted",
                     "sources.list line incorrect, got %s" % line)

if __name__ == "__main__":
    apt_pkg.init()
    apt_pkg.Config.Set("APT::Architecture","amd64")
    unittest.main()
