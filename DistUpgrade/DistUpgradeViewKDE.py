# DistUpgradeViewKDE.py 
#  
#  Copyright (c) 2007 Canonical Ltd
#  
#  Author: Jonathan Riddell <jriddell@ubuntu.com>
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

from qt import *
from kdeui import *
from kdecore import *
from kparts import konsolePart

import sys
import logging
import time
import subprocess
import traceback

import apt
import apt_pkg
import os

import pty

from apt.progress import InstallProgress
from DistUpgradeControler import DistUpgradeControler
from DistUpgradeView import DistUpgradeView, FuzzyTimeToStr, estimatedDownloadTime
from window_main import window_main
from dialog_error import dialog_error
from dialog_changes import dialog_changes
from dialog_conffile import dialog_conffile
from crashdialog import CrashDialog

import gettext
from gettext import gettext as _

def utf8(str):
  return unicode(str, 'latin1').encode('utf-8')

class KDEOpProgress(apt.progress.OpProgress):
  """ methods on the progress bar """
  def __init__(self, progressbar, progressbar_label):
      self.progressbar = progressbar
      self.progressbar_label = progressbar_label
      #self.progressbar.set_pulse_step(0.01)
      #self.progressbar.pulse()

  def update(self, percent):
      #if percent > 99:
      #    self.progressbar.set_fraction(1)
      #else:
      #    self.progressbar.pulse()
      #self.progressbar.set_fraction(percent/100.0)
      self.progressbar.setProgress(percent)
      KApplication.kApplication().processEvents()

  def done(self):
      self.progressbar_label.setText("")

class KDEFetchProgressAdapter(apt.progress.FetchProgress):
    """ methods for updating the progress bar while fetching packages """
    # FIXME: we really should have some sort of "we are at step"
    # xy in the gui
    # FIXME2: we need to thing about mediaCheck here too
    def __init__(self, parent):
        # if this is set to false the download will cancel
        self.status = parent.window_main.label_status
        self.progress = parent.window_main.progressbar_cache
        self.parent = parent

    def mediaChange(self, medium, drive):
      restart = QMessageBox.question(self.window_main, _("Media Change"), msg, QMessageBox.Ok|QMessageBox.Cancel, QMessageBox.Cancel)
      if restart == QMessageBox.Yes:
        return True
      return False

    def start(self):
        #self.progress.show()
        self.progress.setProgress(0)
        self.status.show()

    def stop(self):
        self.parent.window_main.progress_text.setText("  ")
        self.status.setText(_("Fetching is complete"))

    def pulse(self):
        """ we don't have a mainloop in this application, we just call processEvents here and elsewhere"""
        # FIXME: move the status_str and progress_str into python-apt
        # (python-apt need i18n first for this)
        apt.progress.FetchProgress.pulse(self)
        self.progress.setProgress(self.percent)
        currentItem = self.currentItems + 1
        if currentItem > self.totalItems:
            currentItem = self.totalItems

        if self.currentCPS > 0:
            self.status.setText(_("Fetching file %li of %li at %s/s") % (currentItem, self.totalItems, apt_pkg.SizeToStr(self.currentCPS)))
            self.parent.window_main.progress_text.setText("<i>" + _("About %s remaining") % FuzzyTimeToStr(self.eta) + "</i>")
        else:
            self.status.setText(_("Fetching file %li of %li") % (currentItem, self.totalItems))
            self.parent.window_main.progress_text.setText("  ")

        KApplication.kApplication().processEvents()
        return True

class KDEInstallProgressAdapter(InstallProgress):
    """methods for updating the progress bar while installing packages"""
    # timeout with no status change when the terminal is expanded
    # automatically
    TIMEOUT_TERMINAL_ACTIVITY = 240

    def __init__(self,parent):
        InstallProgress.__init__(self)
        self._cache = None
        self.label_status = parent.window_main.label_status
        self.progress = parent.window_main.progressbar_cache
        self.progress_text = parent.window_main.progress_text
        self.parent = parent
        # some options for dpkg to make it die less easily
        apt_pkg.Config.Set("DPkg::Options::","--force-overwrite")
        apt_pkg.Config.Set("DPkg::StopOnError","False")

    def startUpdate(self):
        self.finished = False
        # FIXME: add support for the timeout
        # of the terminal (to display something useful then)
        # -> longer term, move this code into python-apt 
        self.label_status.setText(_("Applying changes"))
        self.progress.setProgress(0)
        self.progress_text.setText(" ")
        frontend="kde"
        self.env = ["VTE_PTY_KEEP_FD=%s"% self.writefd,
                    "DEBIAN_FRONTEND=%s" % frontend,
                    "APT_LISTCHANGES_FRONTEND=none"]
        # do a bit of time-keeping
        self.start_time = 0.0
        self.time_ui = 0.0
        self.last_activity = 0.0

    def error(self, pkg, errormsg):
        logging.error("got an error from dpkg for pkg: '%s': '%s'" % (pkg, errormsg))
        msg="<big><b>%s</b></big><br />%s" % (summary, msg)

        dialogue = dialog_error(self.parent.window_main)
        dialogue.label_error.setText(msg)
        if extended_msg != None:
            dialogue.textview_error.setText(utf8(extended_msg))
            dialogue.textview_error.show()
        else:
            dialogue.textview_error.hide()
        self.connect(dialogue.button_bugreport, SIGNAL("clicked()"), self.parent.reportBug)
        dialogue.exec_loop()

    def conffile(self, current, new):
        """ask question incase conffile has been changed by user"""
        logging.debug("got a conffile-prompt from dpkg for file: '%s'" % current)
        start = time.time()
        prim = _("Replace the customized configuration file\n'%s'?") % current
        sec = _("You will lose any changes you have made to this "
                "configuration file if you choose to replace it with "
                "a newer version.")
        markup = "<span weight=\"bold\" size=\"larger\">%s </span> \n\n%s" % (prim, sec)
        dialogue = dialog_conffile(self.parent.window_main)
        dialogue.label_conffile.setText(markup)

        # now get the diff
        if os.path.exists("/usr/bin/diff"):
          cmd = ["/usr/bin/diff", "-u", current, new]
          diff = utf8(subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0])
          dialogue.textview_conffile.setText(diff)
        else:
          dialogue.textview_conffile.setText(_("The 'diff' command was not found"))
        result = dialogue.exec_loop()
        self.time_ui += time.time() - start
        # if replace, send this to the terminal
        if result == QDialog.Accepted:
            self.parent.konsole.sendInput("y\n")
        else:
            self.parent.konsole.sendInput("n\n")

    def fork(self):
        """pty voodoo to attach dpkg's pty to konsole"""
        self.pid = os.fork()
        if self.pid == 0:
            os.dup2(self.parent.slave, 0)
            os.dup2(self.parent.slave, 1)
            os.dup2(self.parent.slave, 2)
        logging.debug(" fork pid is: %s" % self.pid)
        return self.pid

    def statusChange(self, pkg, percent, status):
        """update progress bar and label"""
        # start the timer when the first package changes its status
        if self.start_time == 0.0:
          #print "setting start time to %s" % self.start_time
          self.start_time = time.time()
        self.progress.setProgress(self.percent)
        self.label_status.setText(status.strip())
        # start showing when we gathered some data
        if percent > 1.0:
          self.last_activity = time.time()
          self.activity_timeout_reported = False
          delta = self.last_activity - self.start_time
          # time wasted in conffile questions (or other ui activity)
          delta -= self.time_ui
          time_per_percent = (float(delta)/percent)
          eta = (100.0 - self.percent) * time_per_percent
          # only show if we have some sensible data (60sec < eta < 2days)
          if eta > 61.0 and eta < (60*60*24*2):
            self.progress_text.setText(_("About %s remaining") % FuzzyTimeToStr(eta))
          else:
            self.progress_text.setText(" ")

    def child_exited(self, term, pid, status):
        self.apt_status = os.WEXITSTATUS(status)
        self.finished = True

    def waitChild(self):
        while not self.finished:
            self.updateInterface()
        return self.apt_status

    def finishUpdate(self):
        self.label_status.setText("")

    def updateInterface(self):
        """no mainloop in this application, just call processEvents lots here, it's also important to sleep for a minimum amount of time"""
        try:
          InstallProgress.updateInterface(self)
        except ValueError, e:
          logging.error("got ValueError from InstallPrgoress.updateInterface. Line was '%s' (%s)" % (self.read, e))
          # reset self.read so that it can continue reading and does not loop
          self.read = ""
        # check if we haven't started yet with packages, pulse then
        if self.start_time == 0.0:
          #Gtk frontend does a pulse here to move bar back and forward, we can't do that in qt
          time.sleep(0.0000001)
        # check about terminal activity
        if self.last_activity > 0 and \
           (self.last_activity + self.TIMEOUT_TERMINAL_ACTIVITY) < time.time():
          if not self.activity_timeout_reported:
            logging.warning("no activity on terminal for %s seconds (%s)" % (self.TIMEOUT_TERMINAL_ACTIVITY, self.label_status.get_text()))
            self.activity_timeout_reported = True
          self.parent.konsole_frame.show()
        KApplication.kApplication().processEvents()
        time.sleep(0.0000001)

    def processExited(self, process):
        """slot called by konsole to tell dpkg the child has finished"""
        self.finished = True
        self.apt_status = process.exitStatus()

class DistUpgradeViewKDE(DistUpgradeView):
    """KDE frontend of the distUpgrade tool"""
    def __init__(self, datadir=None):
        if not datadir:
          localedir=os.path.join(os.getcwd(),"mo")
        else:
          localedir="/usr/share/locale/update-manager"

        # FIXME: i18n must be somewhere relative do this dir
        try:
          bindtextdomain("update-manager", localedir)
          gettext.textdomain("update-manager")
        except Exception, e:
          logging.warning("Error setting locales (%s)" % e)

        about=KAboutData("adept_manager","Upgrader","0.1","Dist Upgrade Tool for Kubuntu",KAboutData.License_GPL,"(c) 2007 Canonical Ltd",
        "http://wiki.kubuntu.org/KubuntuUpdateManager", "jriddell@ubuntu.com")
        about.addAuthor("Jonathan Riddell", None,"jriddell@ubuntu.com")
        KCmdLineArgs.init(["./dist-upgrade.py"],about)

        self.app = KApplication()

        self.mainWindow = KMainWindow()
        self.window_main = window_main(self.mainWindow)
        self.mainWindow.setCentralWidget(self.window_main)
        self.mainWindow.show()

        self.prev_step = 0 # keep a record of the latest step

        self._opCacheProgress = KDEOpProgress(self.window_main.progressbar_cache, self.window_main.progress_text)
        self._fetchProgress = KDEFetchProgressAdapter(self)
        ##FIXME self._cdromProgress = GtkCdromProgressAdapter(self)

        self._installProgress = KDEInstallProgressAdapter(self)

        # reasonable fault handler
        sys.excepthook = self._handleException

        self.box = QHBoxLayout(self.window_main.konsole_frame)
        self.konsole = konsolePart(self.window_main.konsole_frame, "konsole", self.window_main.konsole_frame, "konsole")
        self.konsole.setAutoStartShell(False)
        self.konsoleWidget = self.konsole.widget()
        self.box.addWidget(self.konsoleWidget)
        self.konsoleWidget.show()
        self.app.connect(self.konsole, SIGNAL("processExited(KProcess*)"), self._installProgress.processExited)

        #prepare for dpkg pty being attached to konsole
        (self.master, self.slave) = pty.openpty()
        self.konsole.setPtyFd(self.master)

        self.window_main.konsole_frame.hide()
        self.app.connect(self.window_main.showTerminalButton, SIGNAL("clicked()"), self.showTerminal)

    def _handleException(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
            issubclass(exctype, SystemExit)):
            return

        tbtext = ''.join(traceback.format_exception(exctype, excvalue, exctb))
        logging.error("Exception in KDE frontend (invoking crash handler):")
        logging.error(tbtext)
        dialog = CrashDialog(self.window_main)
        dialog.connect(dialog.beastie_url, SIGNAL("leftClickedURL(const QString&)"), self.openURL)
        dialog.crash_detail.setText(tbtext)
        dialog.exec_loop()
        sys.exit(1)

    def openURL(self, url):
        """start konqueror"""
        #need to run this else kdesu can't run Konqueror
        #subprocess.call(['su', 'ubuntu', 'xhost', '+localhost'])
        KRun.runURL(KURL(url), "text/html")

    def reportBug(self, url):
        """start konqueror"""
        #need to run this else kdesu can't run Konqueror
        #subprocess.call(['su', 'ubuntu', 'xhost', '+localhost'])
        KRun.runURL(KURL("https://launchpad.net/distros/ubuntu/+source/update-manager/+filebug"), "text/html")

    def showTerminal(self):
        if self.window_main.konsole_frame.isVisible():
            self.window_main.konsole_frame.hide()
            self.window_main.showTerminalButton.setText(_("Show Terminal >>>"))
        else:
            self.window_main.konsole_frame.show()
            self.window_main.showTerminalButton.setText(_("<<< Hide Terminal"))

    def getFetchProgress(self):
        return self._fetchProgress

    def getInstallProgress(self, cache):
        self._installProgress._cache = cache
        return self._installProgress

    def getOpCacheProgress(self):
        return self._opCacheProgress

    def updateStatus(self, msg):
        self.window_main.label_status.setText("%s" % msg)

    def hideStep(self, step):
        image = getattr(self.window_main,"image_step%i" % step)
        label = getattr(self.window_main,"label_step%i" % step)
        image.hide()
        label.hide()

    def abort(self):
        step = self.prev_step
        if step > 0:
            image = getattr(self.window_main,"image_step%i" % step)
            iconLoader = KIconLoader()
            cancelIcon = iconLoader.loadIcon("cancel", KIcon.Small)
            image.setPixmap(cancelIcon)
            image.show()

    def setStep(self, step):
        iconLoader = KIconLoader()
        if self.prev_step:
            image = getattr(self.window_main,"image_step%i" % self.prev_step)
            label = getattr(self.window_main,"label_step%i" % self.prev_step)
            okIcon = iconLoader.loadIcon("ok", KIcon.Small)
            image.setPixmap(okIcon)
            image.show()
            ##arrow.hide()
        self.prev_step = step
        # show the an arrow for the current step and make the label bold
        image = getattr(self.window_main,"image_step%i" % step)
        label = getattr(self.window_main,"label_step%i" % step)
        arrowIcon = iconLoader.loadIcon("1rightarrow", KIcon.Small)
        image.setPixmap(arrowIcon)
        image.show()
        label.setText("<b>" + label.text() + "</b>")

    def information(self, summary, msg, extended_msg=None):
        msg = "<big><b>%s</b></big><br />%s" % (summary,msg)
        dialogue = dialog_error(self.window_main)
        dialogue.label_error.setText(msg)
        if extended_msg != None:
            dialogue.textview_error.setText(utf8(extended_msg))
            dialogue.textview_error.show()
        else:
            dialogue.textview_error.hide()
        dialogue.button_bugreport.hide()
        iconLoader = KIconLoader()
        messageIcon = iconLoader.loadIcon("messagebox_info", KIcon.Panel)
        dialogue.image.setPixmap(messageIcon)
        dialogue.exec_loop()

    def error(self, summary, msg, extended_msg=None):
        msg="<big><b>%s</b></big><br />%s" % (summary, msg)

        dialogue = dialog_error(self.window_main)
        dialogue.label_error.setText(msg)
        if extended_msg != None:
            dialogue.textview_error.setText(utf8(extended_msg))
            dialogue.textview_error.show()
        else:
            dialogue.textview_error.hide()
        self.connect(dialogue.button_bugreport, SIGNAL("clicked()"), self.reportBug)
        dialogue.exec_loop()

        return False

    def confirmChanges(self, summary, changes, downloadSize, actions=None):
        """show the changes dialogue"""
        # FIXME: add a whitelist here for packages that we expect to be
        # removed (how to calc this automatically?)
        DistUpgradeView.confirmChanges(self, summary, changes, downloadSize)
        pkgs_remove = len(self.toRemove)
        pkgs_inst = len(self.toInstall)
        pkgs_upgrade = len(self.toUpgrade)
        msg = ""

        if pkgs_remove > 0:
            # FIXME: make those two seperate lines to make it clear
            #        that the "%" applies to the result of ngettext
            msg += gettext.ngettext("%d package is going to be removed.",
                                    "%d packages are going to be removed.",
                                    pkgs_remove) % pkgs_remove
            msg += " "
        if pkgs_inst > 0:
            msg += gettext.ngettext("%d new package is going to be "
                                    "installed.",
                                    "%d new packages are going to be "
                                    "installed.",pkgs_inst) % pkgs_inst
            msg += " "
        if pkgs_upgrade > 0:
            msg += gettext.ngettext("%d package is going to be upgraded.",
                                    "%d packages are going to be upgraded.",
                                    pkgs_upgrade) % pkgs_upgrade
            msg +=" "
        if downloadSize > 0:
            msg += _("<br />You have to download a total of %s. ") %\
                     apt_pkg.SizeToStr(downloadSize)
            msg += estimatedDownloadTime(downloadSize)
            msg += "."

        if (pkgs_upgrade + pkgs_inst + pkgs_remove) > 100:
            msg += "<br />%s" % _("Fetching and installing the upgrade can take several hours and "\
                                "cannot be canceled at any time later.")

        msg += "<br /><b>%s</b>" % _("To prevent data loss close all open "\
                                   "applications and documents.")

        # Show an error if no actions are planned
        if (pkgs_upgrade + pkgs_inst + pkgs_remove) < 1:
            # FIXME: this should go into DistUpgradeController
            summary = _("Your system is up-to-date")
            msg = _("There are no upgrades available for your system. "
                    "The upgrade will now be canceled.")
            self.error(summary, msg)
            return False

        changesDialogue = dialog_changes(self.window_main)

        changesDialogue.label_summary.setText("<big><b>%s</b></big>" % summary)
        changesDialogue.label_changes.setText(msg)
        # fill in the details
        changesDialogue.treeview_details.clear()
        changesDialogue.treeview_details.setColumnText(0, "Packages")
        for rm in self.toRemove:
            changesDialogue.treeview_details.insertItem( QListViewItem(changesDialogue.treeview_details, _("Remove %s") % rm) )
        for inst in self.toInstall:
            changesDialogue.treeview_details.insertItem( QListViewItem(changesDialogue.treeview_details, _("Install %s") % inst) )
        for up in self.toUpgrade:
            changesDialogue.treeview_details.insertItem( QListViewItem(changesDialogue.treeview_details, _("Upgrade %s") % up) )
        res = changesDialogue.exec_loop()
        if res == QDialog.Accepted:
            return True
        return False

    def askYesNoQuestion(self, summary, msg):
        restart = QMessageBox.question(self.window_main, summary, msg, QMessageBox.Yes|QMessageBox.Cancel, QMessageBox.Cancel)
        if restart == QMessageBox.Yes:
            return True
        return False
