# DistUpgradeView.py 
#  
#  Copyright (c) 2004,2005 Canonical
#  
#  Author: Michael Vogt <michael.vogt@ubuntu.com>
# 
#  This program is free software; you can redistribute it and/or 
#  modify it under the terms of the GNU General Public License as 
#  published by the Free Software Foundation; either version 2 of the
#  License, or (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#  USA

import apt
import logging
import time
import sys
from DistUpgradeView import DistUpgradeView, InstallProgress, FetchProgress
from DistUpgradeConfigParser import DistUpgradeConfig
import os
import pty
import apt_pkg
import select
import fcntl
import string
import re
import subprocess
from subprocess import call, PIPE, Popen
import copy
import apt.progress
from ConfigParser import NoSectionError, NoOptionError

class NonInteractiveFetchProgress(FetchProgress):
    def updateStatus(self, uri, descr, shortDescr, status):
        FetchProgress.updateStatus(self, uri, descr, shortDescr, status)
        #logging.debug("Fetch: updateStatus %s %s" % (uri, status))
        if status == apt.progress.FetchProgress.dlDone:
            print "fetched %s (%.2f/100) at %sb/s" % (uri, self.percent, 
                                                      apt_pkg.SizeToStr(int(self.currentCPS)))
            if sys.stdout.isatty():
                sys.stdout.flush()
        

class NonInteractiveInstallProgress(InstallProgress):
    """ 
    Non-interactive version of the install progress class
    
    This ensures that conffile prompts are handled and that
    hanging scripts are killed after a (long) timeout via ctrl-c
    """

    def __init__(self, logdir):
        InstallProgress.__init__(self)
        logging.debug("setting up environ for non-interactive use")
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        os.environ["APT_LISTCHANGES_FRONTEND"] = "none"
        os.environ["RELEASE_UPRADER_NO_APPORT"] = "1"
        self.config = DistUpgradeConfig(".")
        self.logdir = logdir
        self.install_run_number = 0
        try:
            if self.config.getWithDefault("NonInteractive","ForceOverwrite", False):
                apt_pkg.Config.Set("DPkg::Options::","--force-overwrite")
        except (NoSectionError, NoOptionError), e:
            pass
        # more debug
        #apt_pkg.Config.Set("Debug::pkgOrderList","true")
        #apt_pkg.Config.Set("Debug::pkgDPkgPM","true")
        # default to 2400 sec timeout
        self.timeout = 2400
        try:
            self.timeout = self.config.getint("NonInteractive","TerminalTimeout")
        except Exception, e:
            pass
    
    def error(self, pkg, errormsg):
        logging.error("got a error from dpkg for pkg: '%s': '%s'" % (pkg, errormsg))
        # check if re-run of maintainer script is requested
        if not self.config.getWithDefault(
            "NonInteractive","DebugBrokenScripts", False):
            return
        # re-run maintainer script with sh -x/perl debug to get a better 
        # idea what went wrong
        # 
        # FIXME: this is just a approximation for now, we also need
        #        to pass:
        #        - a version after remove (if upgrade to new version)
        #
        #        not everything is a shell or perl script
        #
        # if the new preinst fails, its not yet in /var/lib/dpkg/info
        # so this is inaccurate as well
        environ = copy.copy(os.environ)
        environ["PYCENTRAL"] = "debug"
        cmd = []

        # find what maintainer script failed
        if "post-installation" in errormsg:
            prefix = "/var/lib/dpkg/info/"
            name = "postinst"
            argument = "configure"
            maintainer_script = "%s/%s.%s" % (prefix, pkg, name)
        elif "pre-installation" in errormsg:
            prefix = "/var/lib/dpkg/tmp.ci/"
            #prefix = "/var/lib/dpkg/info/"
            name = "preinst"
            argument = "install"
            maintainer_script = "%s/%s" % (prefix, name)
        elif "pre-removal" in errormsg:
            prefix = "/var/lib/dpkg/info/"
            name = "prerm"
            argument = "remove"
            maintainer_script = "%s/%s.%s" % (prefix, pkg, name)
        elif "post-removal" in errormsg:
            prefix = "/var/lib/dpkg/info/"
            name = "postrm"
            argument = "remove"
            maintainer_script = "%s/%s.%s" % (prefix, pkg, name)
        else:
            print "UNKNOWN (trigger?) dpkg/script failure for %s (%s) " % (pkg, errormsg)
            return

        # find out about the interpreter
        if not os.path.exists(maintainer_script):
            logging.error("can not find failed maintainer script '%s' " % maintainer_script)
            return
        interp = open(maintainer_script).readline()[2:].strip().split()[0]
        if ("bash" in interp) or ("/bin/sh" in interp):
            debug_opts = ["-ex"]
        elif ("perl" in interp):
            debug_opts = ["-d"]
            environ["PERLDB_OPTS"] = "AutoTrace NonStop"
        else:
            logging.warning("unknown interpreter: '%s'" % interp)

        # check if debconf is used and fiddle a bit more if it is
        if ". /usr/share/debconf/confmodule" in open(maintainer_script).read():
            environ["DEBCONF_DEBUG"] = "developer"
            environ["DEBIAN_HAS_FRONTEND"] = "1"
            interp = "/usr/share/debconf/frontend"
            debug_opts = ["sh","-ex"]

        # build command
        cmd.append(interp)
        cmd.extend(debug_opts)
        cmd.append(maintainer_script)
        cmd.append(argument)

        # check if we need to pass a version
        if name == "postinst":
            version = Popen("dpkg-query -s %s|grep ^Config-Version" % pkg,shell=True, stdout=PIPE).communicate()[0]
            if version:
                cmd.append(version.split(":",1)[1].strip())
        elif name == "preinst":
            pkg = os.path.basename(pkg)
            pkg = pkg.split("_")[0]
            version = Popen("dpkg-query -s %s|grep ^Version" % pkg,shell=True, stdout=PIPE).communicate()[0]
            if version:
                cmd.append(version.split(":",1)[1].strip())

        logging.debug("re-running '%s' (%s)" % (cmd, environ))
        ret = subprocess.call(cmd, env=environ)
        logging.debug("%s script returned: %s" % (name,ret))
        
    def conffile(self, current, new):
        logging.warning("got a conffile-prompt from dpkg for file: '%s'" % current)
        # looks like we have a race here *sometimes*
        time.sleep(5)
	try:
          # don't overwrite
	  os.write(self.master_fd,"n\n")
 	except Exception, e:
	  logging.error("error '%s' when trying to write to the conffile"%e)

    def startUpdate(self):
        InstallProgress.startUpdate(self)
        self.last_activity = time.time()
        progress_log = self.config.getWithDefault("NonInteractive","DpkgProgressLog", False)
        if progress_log:
            fullpath = os.path.join(self.logdir, "dpkg-progress.%s.log" % self.install_run_number)
            logging.debug("writing dpkg progress log to '%s'" % fullpath)
            self.dpkg_progress_log = open(fullpath, "w")
        else:
            self.dpkg_progress_log = open(os.devnull, "w")
        self.dpkg_progress_log.write("%s: Start\n" % time.time())
    def finishUpdate(self):
        InstallProgress.finishUpdate(self)
        self.dpkg_progress_log.write("%s: Finished\n" % time.time())
        self.dpkg_progress_log.close()
        self.install_run_number += 1
    def statusChange(self, pkg, percent, status_str):
        self.dpkg_progress_log.write("%s:%s:%s:%s\n" % (time.time(),
                                                        percent,
                                                        pkg,
                                                        status_str))
    def updateInterface(self):
        if self.statusfd == None:
            return

        if (self.last_activity + self.timeout) < time.time():
            logging.warning("no activity %s seconds (%s) - sending ctrl-c" % (self.timeout, self.status))
            # ctrl-c
            os.write(self.master_fd,chr(3))


        # read status fd from dpkg
        # from python-apt/apt/progress.py (but modified a bit)
        # -------------------------------------------------------------
        res = select.select([self.statusfd],[],[],0.1)
        while len(res[0]) > 0:
            self.last_activity = time.time()
            while not self.read.endswith("\n"):
                self.read += os.read(self.statusfd.fileno(),1)
            if self.read.endswith("\n"):
                s = self.read
                #print s
                (status, pkg, percent, status_str) = string.split(s, ":")
                if status == "pmerror":
                    self.error(pkg,status_str)
                elif status == "pmconffile":
                    # we get a string like this:
                    # 'current-conffile' 'new-conffile' useredited distedited
                    match = re.compile("\s*\'(.*)\'\s*\'(.*)\'.*").match(status_str)
                    if match:
                        self.conffile(match.group(1), match.group(2))
                elif status == "pmstatus":
                    if (float(percent) != self.percent or 
                        status_str != self.status):
                        self.statusChange(pkg, float(percent), status_str.strip())
                        self.percent = float(percent)
                        self.status = string.strip(status_str)
                        sys.stdout.write("[%s] %s: %s\n" % (float(percent), pkg, status_str.strip()))
                        sys.stdout.flush()
            self.read = ""
            res = select.select([self.statusfd],[],[],0.1)
        # -------------------------------------------------------------

        #fcntl.fcntl(self.master_fd, fcntl.F_SETFL, os.O_NDELAY)
        # read master fd (terminal output)
        res = select.select([self.master_fd],[],[],0.1)
        while len(res[0]) > 0:
           self.last_activity = time.time()
           try:
               s = os.read(self.master_fd, 1)
               sys.stdout.write("%s" % s)
           except OSError,e:
               # happens after we are finished because the fd is closed
               return
           res = select.select([self.master_fd],[],[],0.1)
        sys.stdout.flush()

    def fork(self):
        logging.debug("doing a pty.fork()")
        # some maintainer scripts fail without
        os.environ["TERM"] = "dumb"
        # unset PAGER so that we can do "diff" in the dpkg prompt
        os.environ["PAGER"] = "true"
        (self.pid, self.master_fd) = pty.fork()
        if self.pid != 0:
            logging.debug("pid is: %s" % self.pid)
        return self.pid
        

class DistUpgradeViewNonInteractive(DistUpgradeView):
    " non-interactive version of the upgrade view "
    def __init__(self, datadir=None, logdir=None):
        self.config = DistUpgradeConfig(".")
        self._fetchProgress = NonInteractiveFetchProgress()
        self._installProgress = NonInteractiveInstallProgress(logdir)
        self._opProgress = apt.progress.OpProgress()
        sys.__excepthook__ = self.excepthook
    def excepthook(self, type, value, traceback):
        " on uncaught exceptions -> print error and reboot "
        logging.exception("got exception '%s': %s " % (type, value))
        #sys.excepthook(type, value, traceback)
        self.confirmRestart()
    def getOpCacheProgress(self):
        " return a OpProgress() subclass for the given graphic"
        return self._opProgress
    def getFetchProgress(self):
        " return a fetch progress object "
        return self._fetchProgress
    def getInstallProgress(self, cache=None):
        " return a install progress object "
        return self._installProgress
    def updateStatus(self, msg):
        """ update the current status of the distUpgrade based
            on the current view
        """
        pass
    def setStep(self, step):
        """ we have 5 steps current for a upgrade:
        1. Analyzing the system
        2. Updating repository information
        3. Performing the upgrade
        4. Post upgrade stuff
        5. Complete
        """
        pass
    def confirmChanges(self, summary, changes, downloadSize,
                       actions=None, removal_bold=True):
        DistUpgradeView.confirmChanges(self, summary, changes, downloadSize, actions)
	logging.debug("toinstall: '%s'" % self.toInstall)
        logging.debug("toupgrade: '%s'" % self.toUpgrade)
        logging.debug("toremove: '%s'" % self.toRemove)
        return True
    def askYesNoQuestion(self, summary, msg, default='No'):
        " ask a Yes/No question and return True on 'Yes' "
        #if default.lower() == "no":
        #    return False
        return True
    def confirmRestart(self):
        " generic ask about the restart, can be overridden "
	logging.debug("confirmRestart() called")
        # rebooting here makes sense if we run e.g. in qemu
        return self.config.getWithDefault("NonInteractive","RealReboot", False)
    def error(self, summary, msg, extended_msg=None):
        " display a error "
        logging.error("%s %s (%s)" % (summary, msg, extended_msg))
    def abort(self):
        logging.error("view.abort called")


if __name__ == "__main__":

  view = DistUpgradeViewNonInteractive()
  fp = NonInteractiveFetchProgress()
  ip = NonInteractiveInstallProgress()

  #ip.error("linux-image-2.6.17-10-generic","post-installation script failed")
  ip.error("xserver-xorg","pre-installation script failed")

  cache = apt.Cache()
  for pkg in sys.argv[1:]:
    #if cache[pkg].isInstalled:
    #  cache[pkg].markDelete()
    #else:
    cache[pkg].markInstall()
  cache.commit(fp,ip)
  time.sleep(2)
  sys.exit(0)
