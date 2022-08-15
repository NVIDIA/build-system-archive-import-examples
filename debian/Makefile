PWD = $(shell pwd)
VERSION = 1.0-1
GPG_HEADLESS = --openpgp --decrypt --no-auto-check-trustdb --batch --no-tty --status-fd 1

DEB_ROOT	= example
DEB_ARCH	= all
IN_FILES	= $(wildcard $(DEB_ROOT)/debian/templates/*.install.in)
DEB_PACKAGE	= $(join $(addsuffix ../../, $(dir $(IN_FILES))), $(notdir $(IN_FILES:.install.in=_$(VERSION)_$(DEB_ARCH).deb)))

META_ROOT	= meta

default: all

$(DEB_PACKAGE): $(IN_FILES)
	cd $(DEB_ROOT)/; make -f debian/rules fill_templates VERSION=1.0
	cd $(DEB_ROOT)/; dpkg-buildpackage -b -us -uc
	mv *.deb *.buildinfo *.changes $(DEB_ROOT)/
	cd $(DEB_ROOT)/; rm -rf debian/`basename $< | cut -d. -f1`

all: $(DEB_PACKAGE) Release trash
	@for deb in $(DEB_PACKAGE); do ar -p "$(DEB_PACKAGE)" _gpgbuilder 2>&1 | GNUPGHOME=/dev/null gpg $GPG_HEADLESS 2>&1 | grep -q "[GNUPG:\] NO_PUBKEY" || echo "UNSIGNED `basename $(DEB_PACKAGE)`"; done
	@#ls -1 $(META_DATA)

debian: $(DEB_PACKAGE)

Release: $(DEB_PACKAGE)
	@for pkg in $(DEB_PACKAGE); do deb=`readlink -m $$pkg`; ln -s -f $$deb $(META_ROOT)/`basename $$deb`; done
	cd $(META_ROOT); ./stubrepo-debian.sh *.deb

meta: Release

trash:
	cd $(DEB_ROOT)/; rm -f *.changes *.buildinfo
	cd $(DEB_ROOT)/; rm -f debian/changelog debian/control debian/*.log debian/*.install debian/*.substvars debian/files
	cd $(DEB_ROOT)/; rm -rf debian/example debian/.debhelper

clean: trash
	rm -f $(META_ROOT)/Packages $(META_ROOT)/Packages.gz
	rm -f $(META_ROOT)/Release
	rm -f $(META_ROOT)/Release.gpg $(META_ROOT)/InRelease
	rm -f $(META_ROOT)/*.deb
	rm -f $(DEB_ROOT)/*.deb

.PHONY: all default debian meta trash clean
