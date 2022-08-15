#!/bin/bash

repo_origin="EXAMPLE"
repo_label="Unstable"
pkg_arch="all"
pkg_date=$(date -R -u)

err() { echo "ERROR: $*"; exit 1; }

find_tag() {
    local index=0
    for key in ${pkg_tags[@]}; do
        if [[ "$key" == "null" ]]; then
            pkg_tags[$index]="null"
        elif [[ "$key" == "$1" ]] || [[ -z "$1" ]]; then
            value=$(dpkg-deb --field "$filename" "$key")
            echo "$key: $value"
            pkg_tags[$index]="null"
        fi
        index=$((index+1))
    done
}

deb_pkg_info() {
    [[ -f "$1" ]] || err "deb_pkg_info() file $1 not found"

    # Calculate some values
    pkg_size=$(du -b "$1" 2>/dev/null | awk '{print $1}')
    pkg_md5=$(md5sum "$1" 2>/dev/null | awk '{print $1}')
    pkg_sha1=$(sha1sum "$1" 2>/dev/null | awk '{print $1}')
    pkg_sha256=$(sha256sum "$1" 2>/dev/null | awk '{print $1}')
    pkg_sha512=$(sha512sum "$1" 2>/dev/null | awk '{print $1}')

    # Order matters
    filename="$1"
    pkg_tags=($(dpkg --info "$filename" | sed 's/^ //' | grep -E "^[A-Za-z-]+:" | awk -F ":" '{print $1}'))
    taglist="Package Version Architecture Multi-Arch Priority Section Source Origin Maintainer Original-Maintainer"
    taglist+="Bugs Installed-Size Provides Depends Recommends Suggests Conflicts Breaks Replaces"
    for tag in $taglist; do
        find_tag $tag
    done

    # Append calculated values
    echo "Filename: ./$1"
    echo "Size: $pkg_size"
    echo "MD5sum: $pkg_md5"
    echo "SHA1: $pkg_sha1"
    echo "SHA256: $pkg_sha256"
    echo "SHA512: $pkg_sha512"

    # Append package description
    find_tag "Homepage"
    find_tag "Description"

    # Anything leftover
    find_tag
}

deb_metadata()
{
    local Packages="$1"
    [[ -f "$Packages" ]] || err "Packages file not found"

    # Compress manifest
    gzip -c -9 -f $Packages > ${Packages}.gz
    echo ":: ${Packages}.gz"
    [[ -f "Packages.gz" ]] || err "Packages.gz file not found"

    # Calculate hashes
    txt_bytes=$(wc --bytes Packages | awk '{print $1}')
    txt_md5=$(md5sum Packages | awk '{print $1}')
    txt_sha1=$(sha1sum Packages | awk '{print $1}')
    txt_sha256=$(sha256sum Packages | awk '{print $1}')

    gz_bytes=$(wc --bytes Packages.gz | awk '{print $1}')
    gz_md5=$(md5sum Packages.gz | awk '{print $1}')
    gz_sha1=$(sha1sum Packages.gz | awk '{print $1}')
    gz_sha256=$(sha256sum Packages.gz | awk '{print $1}')

    # Build checksum file
    pkg_arch=$(basename "$subpath")
    pkg_date=$(date -R -u)

    {
      echo "Origin: ${repo_origin}"
      echo "Label: ${repo_label}"
      echo "Architecture: ${pkg_arch}"
      echo "Date: ${pkg_date}"
      echo "MD5Sum:"
      printf " %s %48d %s\n" $txt_md5 $txt_bytes Packages
      printf " %s %48d %s\n" $gz_md5 $gz_bytes Packages.gz
      echo "SHA1:"
      printf " %s %40d %s\n" $txt_sha1 $txt_bytes Packages
      printf " %s %40d %s\n" $gz_sha1 $gz_bytes Packages.gz
      echo "SHA256:"
      printf " %s %16d %s\n" $txt_sha256 $txt_bytes Packages
      printf " %s %16d %s\n" $gz_sha256 $gz_bytes Packages.gz

      # FIXME prevent hash mismatch error
      echo "Acquire-By-Hash: no"
    } > "Release"
}

if [[ -z $1 ]] || [[ ! -f $1 ]]; then
    err "USAGE: $0 [*.deb]"
fi

if [[ ! -f "Package" ]]; then
    for package in $@; do
        deb_pkg_info "$package" >> Packages
    done
fi

if [[ ! -f "Release" ]]; then
    deb_metadata "Packages"
fi

### END ###
