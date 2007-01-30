#!/bin/sh

DIST=feisty

# cleanup
echo "Cleaning up"
rm -f *~ *.bak *.pyc *.moved '#'* *.rej *.orig
#sudo rm -rf backports/ profile/ result/ tarball/ *.deb

# update po
(cd ../po; make update-po)

# make the kde-gui
for file in *ui; do kdepyuic $${file}; done

# copy the mo files
cp -r ../po/mo .

# make symlink
if [ ! -h $DIST ]; then
	ln -s dist-upgrade.py $DIST
fi

# create the tarball, copy links in place 
tar -c -h -z -v --exclude=$DIST.tar.gz --exclude=$0 -X build-exclude.txt -f $DIST.tar.gz  .


