#!/bin/sh

set -e

# The testsuite has a sad if you're in a non-UTF-8 locale:
export LANG='C.UTF-8'

dpkg-checkbuilddeps -d 'python3-apt, apt-btrfs-snapshot, parsewiki, python3-feedparser,
			python3-mock, xvfb, gir1.2-gtk-3.0, python3-gi, python3-nose, pep8, python3-distutils-extra, python3-update-manager'

# update demotions
# echo "Running demotions"
(cd utils && ./demotions.py cosmic disco > demoted.cfg)
# when this gets enabled, make sure to add symlink in DistUpgrade
# echo "Running lts demotions"
#(cd utils && ./demotions.py xenial bionic > demoted.cfg.xenial)

# update apt_btrfs_snapshot.py copy, this needs an installed
# apt-btrfs-snapshot on the build machine
if [ ! -e /usr/lib/python3/dist-packages/apt_btrfs_snapshot.py ]; then
    echo "please sudo apt-get install apt-btrfs-snapshot"
    exit 1
fi
cp /usr/lib/python3/dist-packages/apt_btrfs_snapshot.py DistUpgrade

# (auto) generate the required html
if [ ! -x /usr/bin/parsewiki ]; then
    echo "please sudo apt-get install parsewiki"
    exit 1
fi
# confirm we have the release version appearing the right number of times in each Announcement
DEBRELEASE=$(LC_ALL=C dpkg-parsechangelog | sed -n -e '/^Distribution:/s/^Distribution: //p' | sed s/-.\*//)
(cd DistUpgrade;
 if [ $(grep -ic $DEBRELEASE DevelReleaseAnnouncement) != 1 ]; then
    echo "Confirm $DEBRELEASE is correct in DevelReleaseAnnouncement"
    exit 1
 fi
 parsewiki DevelReleaseAnnouncement > DevelReleaseAnnouncement.html;
 if [ $(grep -ic $DEBRELEASE ReleaseAnnouncement) != 3 ]; then
    echo "Confirm $DEBRELEASE is correct in ReleaseAnnouncement"
    exit 1
 fi
 parsewiki ReleaseAnnouncement > ReleaseAnnouncement.html;
 if [ $(grep -ic $DEBRELEASE EOLReleaseAnnouncement) != 1 ]; then
    echo "Confirm $DEBRELEASE is correct in EOLReleaseAnnouncement"
    exit 1
 fi
 parsewiki EOLReleaseAnnouncement > EOLReleaseAnnouncement.html;
)

# cleanup
rm -rf utils/apt/lists utils/apt/*.bin
# echo "Running update mirrors"
(cd utils && ./update_mirrors.py ../data/mirrors.cfg)

# run the test-suite
# echo "Running integrated tests"
xvfb-run nosetests3

# test leftovers
# echo "Cleaning up after tests"
rm -f ./tests/data-sources-list-test/apt.log
rm -f ./tests/data-sources-list-test/Ubuntu.mirrors

# update version
DEBVER=$(LC_ALL=C dpkg-parsechangelog |sed -n -e '/^Version:/s/^Version: //p' | sed s/.*://)
echo "VERSION = '$DEBVER'" > DistUpgrade/DistUpgradeVersion.py
