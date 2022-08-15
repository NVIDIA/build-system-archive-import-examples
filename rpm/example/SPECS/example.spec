%global _enable_debug_package 0
%global debug_package %{nil}
%global __os_install_post /usr/lib/rpm/brp-compress %{nil}

Name:       example
Version:    1.0
Release:    1
License:    None
BuildArch:  noarch
Summary:    Unit test for RPM packaging
AutoReq:    0

%description
Example package for test of RPM package signing

%files
