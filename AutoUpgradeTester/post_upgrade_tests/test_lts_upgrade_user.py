#!/usr/bin/python
#
# This script checks user configuration settings after an Ubuntu 10.04
# LTS to Ubuntu 12.04 LTS upgrade. Run prepare_lts_upgrade_user.sh in 10.04
# LTS, then upgrade to 12.04 LTS (or later), and run this script to confirm
# that settings were migrated properly. In particular this checks for gconf ->
# gsettings migration (and sometimes changing the format of the values) for
# popular settings, as well as custom panel/desktop launchers.
#
# You need to run both the prepare and this test script as the same user,
# in a full desktop session.
#
# (C) 2012 Canonical Ltd.
# Author: Martin Pitt <martin.pitt@ubuntu.com>
# License: GPL v2 or higher

import unittest
import os, sys
import subprocess

try:
    from gi.repository import Gio
except:
    # Not a desktop
    print "Failed to import gi.repository. Not a LTS Desktop Upgrade. Skipping!"
    sys.exit(0)

class T(unittest.TestCase):
    def test_background(self):
        '''background image'''

        bg_settings = Gio.Settings('org.gnome.desktop.background')
        # note: original gconf value does not have a file:// prefix, but GNOME
        # 3.x requires this prefix
        self.assertEqual(bg_settings.get_string('picture-uri'),
                'file://%s/mybackground.jpg' % os.environ['HOME'])

    def test_gtk_theme(self):
        '''GTK theme'''

        iface_settings = Gio.Settings('org.gnome.desktop.interface')
        self.assertEqual(iface_settings.get_string('gtk-theme'), 'Radiance')

    def test_custom_launchers(self):
        '''Custom panel/desktop launchers appear in Unity launcher'''

        launcher_settings = Gio.Settings('com.canonical.Unity.Launcher')
        favorites = launcher_settings['favorites']

        # gedit was dragged from Application menu to panel, pointing to system
        # .desktop file
        self.assertTrue('gedit.desktop' in favorites)

        # custom "echo hello" panel starter uses its own .desktop file
        for starter in favorites:
            if 'echo' in starter:
                self.assertTrue(os.path.exists(starter))
                break
        else:
            self.fail('custom hello starter not found')

        # gucharmap was dragged from Application menu to desktop, should be
        # converted to system .desktop file
        self.assertTrue('gucharmap.desktop' in favorites)

        # custom "bc -l" desktop starter uses its own .desktop file
        self.assertTrue('%s/Desktop/termcalc.desktop' % os.environ['HOME'] in favorites)

    def test_keyboard_layouts(self):
        '''Custom keyboard layouts are migrated and applied'''

        # verify gconf->gsettings migration
        kbd_settings = Gio.Settings('org.gnome.libgnomekbd.keyboard')
        self.assertEqual(kbd_settings['layouts'],
                '[us,de\tnodeadkeys,gb,gb\tdvorak]')

# NO DISPLAY IN AUTOMATED TEST
#        # verify that they get applied to the X server correctly
#        xprop = subprocess.Popen(['xprop', '-root', '_XKB_RULES_NAMES'],
#                stdout=subprocess.PIPE)
#        out = xprop.communicate()[0]
#        self.assertEqual(xprop.returncode, 0)
#
#        # chop off key name
#        out = out.split('=', 1)[1].strip()
#
#        self.assertEqual(out, '"evdev", "pc105", "us,de,gb,gb", ",nodeadkeys,,dvorak", "grp:alts_toggle"')

# Only run on lts-ubuntu testcases
if not os.path.exists('/upgrade-tester/prepare_lts_desktop'):
    print "Not an Ubuntu Desktop LTS upgrade. Skipping!"
    sys.exit(0)

if os.getuid() == 0:
    # Root ? reexecute itself as user ubuntu
    subprocess.call('sudo -H -u ubuntu dbus-launch %s' % os.path.abspath(__file__), shell=True)
else:
    unittest.main()
