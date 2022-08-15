PWD = $(shell pwd)
VERSION = 1.0-1
GPG_HEADLESS = --openpgp --decrypt --no-auto-check-trustdb --batch --no-tty --status-fd 1

RPM_ROOT	= example
RPM_ARCH	= noarch
SPEC_FILES 	= $(wildcard $(RPM_ROOT)/SPECS/*.spec)
RPM_PACKAGE	= $(join $(addsuffix ../RPMS/$(RPM_ARCH)/, $(dir $(SPEC_FILES))), $(notdir $(SPEC_FILES:.spec=-$(VERSION).$(RPM_ARCH).rpm)))

META_ROOT	= meta

default: all

$(RPM_PACKAGE): $(SPEC_FILES)
	cd $(RPM_ROOT); rpmbuild --define "%_topdir $(PWD)/$(RPM_ROOT)" -v -ba SPECS/$(shell basename $<)

all: $(RPM_PACKAGE) repodata/repomd.xml trash
	@for rpm in $(RPM_PACKAGE); do rpm -Kv "$(RPM_PACKAGE)" 2>&1 | grep -q "NOKEY" || echo "UNSIGNED `basename $(RPM_PACKAGE)`"; done
	@#ls -1 $(META_DATA)

rpm: $(RPM_PACKAGE)

repodata/repomd.xml: $(RPM_PACKAGE)
	@for pkg in $(RPM_PACKAGE); do rpm=`readlink -m $$pkg`; ln -s -f $$rpm $(META_ROOT)/`basename $$rpm`; done
	cd $(META_ROOT); ./stubrepo-rpm.sh *.rpm

meta: repodata/repomd.xml

trash:
	cd $(RPM_ROOT)/; rm -rf BUILD BUILDROOT SRPMS
	cd $(META_ROOT)/; rm -f repodata/*sqlite.bz2 repodata/*.xml.gz

clean: trash
	rm -f $(META_ROOT)/Packages $(META_ROOT)/Packages.gz
	rm -f $(META_ROOT)/repodata/repomd.xml
	rm -f $(META_ROOT)/repodata/repomd.xml.asc $(META_ROOT)/repodata/repomd.xml.key
	rm -f $(META_ROOT)/*.rpm
	rm -f $(RPM_ROOT)/RPMS/*/*.rpm

.PHONY: all default rpm meta trash clean
