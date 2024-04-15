#!/usr/bin/env python3
# Copyright 2021, NVIDIA Corporation
# SPDX-License-Identifier: MIT
"""
Sample parser for redistrib JSON manifests
1. Downloads each archive
2. Validates SHA256 checksums
3. Extracts archives
4. Flattens into a collapsed directory structure
"""

import argparse
import os
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
import sys
from urllib.request import urlopen

__version__ = "0.4.0"

ARCHIVES = {}
DOMAIN = "https://developer.download.nvidia.com"


def err(msg):
    """Print error message and exit"""
    print("ERROR: " + msg)
    sys.exit(1)


def fetch_file(full_path, filename):
    """Download file to disk"""
    download = urlopen(full_path)
    if download.status != 200:
        print("  -> Failed: " + filename)
    else:
        print(":: Fetching: " + full_path)
        with open(filename, "wb") as file:
            file.write(download.read())
            print("  -> Wrote: " + filename)


def get_hash(filename):
    """Calculate SHA256 checksum for file"""
    buffer_size = 65536
    sha256 = hashlib.sha256()
    with open(filename, "rb") as file:
        while True:
            chunk = file.read(buffer_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def check_hash(filename, checksum):
    """Compare checksum with expected"""
    sha256 = get_hash(filename)
    if checksum == sha256:
        print("	 Verified sha256sum: " + sha256)
    else:
        print("  => Mismatch sha256sum:")
        print("	-> Calculation: " + sha256)
        print("	-> Expectation: " + checksum)


def check_size(filename, size):
    """Compare file size with expected"""
    bytes = str(os.stat(filename).st_size)
    if size == bytes:
        print("	 Verified size: " + bytes)
    else:
        print("  => Mismatch bytes:")
        print("	-> Calculation: " + bytes)
        print("	-> Expectation: " + size)


def flatten_tree(src, dest, tag=None):
    """Merge hierarchy from multiple directories"""
    if tag:
        dest += "/" + tag

    try:
        shutil.copytree(src, dest, symlinks=1, dirs_exist_ok=1, ignore_dangling_symlinks=1)
    except FileExistsError:
        pass
    shutil.rmtree(src)


def parse_artifact(
    parent, manifest, component, platform, retrieve=True, validate=True, variant=None
):
    if variant:
        full_path = parent + manifest[component][platform][variant]["relative_path"]
    else:
        full_path = parent + manifest[component][platform]["relative_path"]

    filename = os.path.basename(full_path)
    file_path = filename
    pwd = os.path.join(os.getcwd(), component, platform)

    if (
        retrieve
        and not os.path.exists(filename)
        and not os.path.exists(parent + filename)
        and not os.path.exists(pwd + filename)
    ):
        # Download archive
        fetch_file(full_path, filename)
        file_path = filename
        ARCHIVES[platform].append(filename)
    elif os.path.exists(filename):
        print("  -> Found: " + filename)
        file_path = filename
        ARCHIVES[platform].append(filename)
    elif os.path.exists(os.path.join(parent, filename)):
        file_path = os.path.join(parent, filename)
        print("  -> Found: " + file_path)
        ARCHIVES[platform].append(file_path)
    elif os.path.exists(os.path.join(pwd, filename)):
        file_path = os.path.join(pwd, filename)
        print("  -> Found: " + file_path)
        ARCHIVES[platform].append(parent + filename)
    else:
        print("Parent: " + os.path.join(pwd, filename))
        print("  -> Artifact: " + filename)

    if validate and os.path.exists(file_path):
        if variant:
            checksum = manifest[component][platform][variant]["sha256"]
            size = manifest[component][platform][variant]["size"]
        else:
            checksum = manifest[component][platform]["sha256"]
            size = manifest[component][platform]["size"]

        # Compare checksum
        check_hash(file_path, checksum)
        check_size(file_path, size)


def fetch_action(parent, manifest, component_filter, platform_filter, retrieve, validate):
    """Do actions while parsing JSON"""
    for component in manifest.keys():
        if not "name" in manifest[component]:
            continue

        if component_filter is not None and component != component_filter:
            continue

        print("\n" + manifest[component]["name"] + ": " + manifest[component]["version"])

        for platform in manifest[component].keys():
            if "variant" in platform:
                continue

            if not platform in ARCHIVES:
                ARCHIVES[platform] = []

            if not isinstance(manifest[component][platform], str):
                if platform_filter is not None and platform != platform_filter:
                    print("  -> Skipping platform: " + platform)
                    continue

                if not "relative_path" in manifest[component][platform]:
                    for variant in manifest[component][platform].keys():
                        parse_artifact(
                            parent,
                            manifest,
                            component,
                            platform,
                            retrieve,
                            validate,
                            variant,
                        )
                else:
                    parse_artifact(parent, manifest, component, platform, retrieve, validate)


def post_action(output_dir, collapse=True):
    """Extract archives and merge directories"""
    if len(ARCHIVES) == 0:
        return

    print("\nArchives:")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for platform in ARCHIVES:
        for archive in ARCHIVES[platform]:
            try:
                binTag = archive.split("-")[3].split("_")[1]
                print(platform, binTag)
            except:
                binTag = None

            # Tar files
            if re.search(r"\.tar\.", archive):
                print(":: tar: " + archive)
                tarball = tarfile.open(archive)
                topdir = os.path.commonprefix(tarball.getnames())
                tarball.extractall()
                tarball.close()
                print("  -> Extracted: " + topdir + "/")
                if collapse:
                    flatten_tree(topdir, output_dir + "/" + platform, binTag)

            # Zip files
            elif re.search(r"\.zip", archive):
                print(":: zip: " + archive)
                with zipfile.ZipFile(archive) as zippy:
                    topdir = os.path.commonprefix(zippy.namelist())
                    zippy.extractall()
                zippy.close()

                print("  -> Extracted: " + topdir)
                if collapse:
                    flatten_tree(topdir, output_dir + "/" + platform, binTag)

    print("\nOutput: " + output_dir + "/")
    for item in sorted(os.listdir(output_dir)):
        if os.path.isdir(output_dir + "/" + item):
            print(" - " + item + "/")
        elif os.path.isfile(output_dir + "/" + item):
            print(" - " + item)


def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser()
    # Input options
    parser_group = parser.add_mutually_exclusive_group(required=True)
    parser_group.add_argument("-u", "--url", dest="url", help="URL to manifest")
    parser_group.add_argument("-l", "--label", dest="label", help="Release label version")
    parser.add_argument("-p", "--product", dest="product", help="Product name")
    parser.add_argument("-o", "--output", dest="output", help="Output directory")
    # Filter options
    parser.add_argument("--component", dest="component", help="Component name")
    parser.add_argument("--os", dest="os", help="Operating System")
    parser.add_argument("--arch", dest="arch", help="Architecture")
    # Toggle actions
    parser.add_argument(
        "-w",
        "--download",
        dest="retrieve",
        action="store_true",
        help="Download archives",
        default=True,
    )
    parser.add_argument(
        "-W",
        "--no-download",
        dest="retrieve",
        action="store_false",
        help="Parse manifest without downloads",
    )
    parser.add_argument(
        "-s",
        "--checksum",
        dest="validate",
        action="store_true",
        help="Verify SHA256 checksum",
        default=True,
    )
    parser.add_argument(
        "-S",
        "--no-checksum",
        dest="validate",
        action="store_false",
        help="Skip SHA256 checksum validation",
    )
    parser.add_argument(
        "-x",
        "--extract",
        dest="unrolled",
        action="store_true",
        help="Extract archives",
        default=True,
    )
    parser.add_argument(
        "-X",
        "--no-extract",
        dest="unrolled",
        action="store_false",
        help="Do not extract archives",
    )
    parser.add_argument(
        "-f",
        "--flatten",
        dest="collapse",
        action="store_true",
        help="Collapse directories",
        default=True,
    )
    parser.add_argument(
        "-F",
        "--no-flatten",
        dest="collapse",
        action="store_false",
        help="Do not collapse directories",
    )

    args = parser.parse_args()

    #
    # Setup
    #

    component = args.component

    # Deduce the platform from both --os and --arch if passed
    # note: os_ to not shadow the os module
    os_ = args.os
    arch = args.arch
    if arch is not None and os_ is not None:
        platform = f"{os_}-{arch}"
    elif arch is not None and os_ is None:
        err("Must pass --os argument")
    elif os_ is not None and arch is None:
        err("Must pass --arch argument")
    else:
        # if both are None we ignore the platform filter
        platform = None

    if args.output is not None:
        output_dir = args.output
    else:
        output_dir = "flat"

    # Get the manifest path from either --url or --label with --product
    if args.url is not None:
        manifest_uri = args.url
    elif args.label is not None:
        if args.product is not None:
            manifest_uri = f"{DOMAIN}/compute/{args.product}/redist/redistrib_{args.label}.json"
        else:
            err("Must pass --product argument")

    if args.retrieve is not None:
        retrieve = args.retrieve
    else:
        retrieve = True
    if args.validate is not None:
        validate = args.validate
    else:
        validate = True

    if args.unrolled is not None:
        unrolled = args.unrolled
    else:
        unrolled = True
    if args.collapse is not None:
        collapse = args.collapse
    else:
        collapse = True

    #
    # Run
    #

    # Parse JSON
    if os.path.isfile(manifest_uri):
        with open(manifest_uri, "rb") as f:
            manifest = json.load(f)
    else:
        try:
            manifest_response = urlopen(manifest_uri)
            manifest = json.loads(manifest_response.read())
        except json.decoder.JSONDecodeError:
            err("redistrib JSON manifest file not found")

    print(":: Parsing JSON: " + manifest_uri)

    # Do stuff
    fetch_action(
        os.path.dirname(manifest_uri) + "/",
        manifest,
        component,
        platform,
        retrieve,
        validate,
    )
    if unrolled:
        post_action(output_dir, collapse)

    ### END ###


if __name__ == "__main__":
    main()
