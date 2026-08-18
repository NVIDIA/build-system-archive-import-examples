#!/usr/bin/env python3
# Copyright 2021, NVIDIA Corporation
# SPDX-License-Identifier: MIT
"""
Sample parser for redistrib JSON manifests
1. Downloads each archive
2. Validates file size in bytes
3. Validates SHA256 checksums
4. Extracts archives
5. Flattens into a collapsed directory structure
"""

__version__ = "0.7.0"
minimum = "3.8"

"""
Sanity check
"""
import sys

if sys.version_info < tuple(map(int, minimum.split("."))):
    print(
        "ERROR: script", __file__, "version", __version__, "requires Python %s or later" % minimum
    )
    sys.exit(1)

import argparse
import os
import stat
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from urllib.parse import urljoin
from urllib.request import urlopen


ARCHIVES = {}
# Seconds to wait for a network connection/response before giving up
TIMEOUT = 30
DOMAIN = "https://developer.download.nvidia.com"
DOMAIN_HOST_ENV = "DOMAIN_HOST"
CHANNELS_DOMAIN = os.environ.get(DOMAIN_HOST_ENV, "https://packages.nvidia.com")


def err(msg):
    """Print error message and exit"""
    print("ERROR: " + msg)
    sys.exit(1)


def fetch_file(full_path, filename):
    """Download file to disk"""
    download = urlopen(full_path, timeout=TIMEOUT)
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


def fix_permissions(directory):
    """Fix for read-only files chmod u+w"""
    for root, dirs, files in os.walk(directory):
        for file in files:
            filename = os.path.join(root, file)
            octal = os.stat(filename)
            os.chmod(filename, octal.st_mode | stat.S_IWRITE)


def flatten_tree(src, dest, tag=None):
    """Merge hierarchy from multiple directories"""
    if tag:
        dest = os.path.join(dest, tag)

    try:
        shutil.copytree(src, dest, symlinks=1, dirs_exist_ok=1, ignore_dangling_symlinks=1)
    except FileExistsError:
        pass
    shutil.rmtree(src)


def resolve(parent, relative_path):
    """Join a component relative_path onto the manifest's parent location.

    Manifests served from the Repo Channels CDN reference pool artifacts
    with dot-segment relative paths (e.g. ../../../pool/...).
    urljoin() collapses those per RFC 3986 so urlopen() requests the real
    path; a raw string concat would send a literal ../ that the CDN 404s.
    Local filesystem manifests keep the plain join.
    """
    if "://" in parent:
        return urljoin(parent, relative_path)
    return parent + relative_path


def load_json_uri(uri):
    """Read and parse a JSON document from a local path or URL"""
    try:
        if os.path.isfile(uri):
            with open(uri, "rb") as file:
                return json.load(file)
        return json.loads(urlopen(uri, timeout=TIMEOUT).read())
    except OSError as error:
        message = "unable to fetch " + uri + " (" + str(error) + ")"
        if uri.startswith(CHANNELS_DOMAIN) and DOMAIN_HOST_ENV not in os.environ:
            message += (
                "\n  -> the Repo Channels CDN may not be published yet; set "
                + DOMAIN_HOST_ENV
                + " to target another host"
            )
        err(message)
    except json.decoder.JSONDecodeError:
        err("invalid JSON at " + uri)


def version_key(version):
    """Sort key that orders numeric version components numerically"""
    key = []
    for part in str(version).split("."):
        key.append((0, int(part)) if part.isdigit() else (1, part))
    return key


def release_base(domain, product):
    """Discovery root for a product on the Repo Channels CDN"""
    return f"{domain}/bin-archive/release/{product}/"


def list_channels(domain, product=None):
    """Print channels (and per-product versions) discoverable on the CDN"""
    channels = load_json_uri(f"{domain}/bin-archive/release/channels.json")
    print(":: Channels:")
    for channel, products in channels.items():
        names = ", ".join(entry.get("product", "?") for entry in products)
        print(f"  - {channel}  [{names}]")

    if product is not None:
        releases = load_json_uri(release_base(domain, product) + "releases.json")
        print("\n:: Releases (" + product + "):")
        for channel, entries in releases.items():
            versions = ", ".join(entry.get("version", "?") for entry in entries)
            print(f"  - {channel}: {versions}")


def discover_release(domain, product, channel, label=None):
    """Resolve a channel + version to its content-addressed (CAS) manifest.

    Reads {product}/releases.json, selects the requested version (or the
    highest when --label is omitted), and returns the CAS manifest URL plus
    the expected sha256/size so the caller can verify the fetched bytes.
    """
    releases = load_json_uri(release_base(domain, product) + "releases.json")
    if channel not in releases:
        err("channel '" + channel + "' not found for product '" + product + "'")

    entries = releases[channel]
    if label is not None:
        entries = [entry for entry in entries if entry.get("version") == label]
        if not entries:
            err("version '" + label + "' not found in channel '" + channel + "'")
    if not entries:
        err("channel '" + channel + "' has no releases for product '" + product + "'")

    entry = sorted(entries, key=lambda item: version_key(item.get("version", "")))[-1]
    if "manifest" not in entry:
        err("release entry for channel '" + channel + "' is missing a manifest path")
    if entry.get("sha256") is None or entry.get("size") is None:
        err("release entry for channel '" + channel + "' is missing CAS metadata (sha256/size)")
    manifest_uri = urljoin(release_base(domain, product), entry["manifest"])
    return manifest_uri, entry["sha256"], entry["size"]


def parse_artifact(
    parent,
    manifest,
    component,
    platform,
    retrieve=True,
    integrity=True,
    validate=True,
    variant=None,
):
    if variant:
        full_path = resolve(parent, manifest[component][platform][variant]["relative_path"])
    else:
        full_path = resolve(parent, manifest[component][platform]["relative_path"])

    filename = os.path.basename(full_path)
    file_path = filename
    pwd = os.path.join(os.getcwd(), component, platform)

    if (
        retrieve
        and not os.path.exists(filename)
        and not os.path.exists(full_path)
        and not os.path.exists(parent + filename)
        and not os.path.exists(os.path.join(pwd, filename))
    ):
        # Download archive
        fetch_file(full_path, filename)
        file_path = filename
        ARCHIVES[platform].append(filename)
    elif os.path.exists(filename):
        print("  -> Found: " + filename)
        file_path = filename
        ARCHIVES[platform].append(filename)
    elif os.path.exists(full_path):
        file_path = full_path
        print("  -> Found: " + file_path)
        ARCHIVES[platform].append(file_path)
    elif os.path.exists(os.path.join(parent, filename)):
        file_path = os.path.join(parent, filename)
        print("  -> Found: " + file_path)
        ARCHIVES[platform].append(file_path)
    elif os.path.exists(os.path.join(pwd, filename)):
        file_path = os.path.join(pwd, filename)
        print("  -> Found: " + file_path)
        ARCHIVES[platform].append(file_path)
    else:
        print("Parent: " + os.path.join(pwd, filename))
        print("  -> Artifact: " + filename)

    if integrity and os.path.exists(file_path):
        if variant:
            size = manifest[component][platform][variant]["size"]
        else:
            size = manifest[component][platform]["size"]

        # Compare size
        check_size(file_path, size)

    if validate and os.path.exists(file_path):
        if variant:
            checksum = manifest[component][platform][variant]["sha256"]
        else:
            checksum = manifest[component][platform]["sha256"]

        # Compare checksum
        check_hash(file_path, checksum)


def fetch_action(
    parent, manifest, component_filter, platform_filter, cuda_filter, retrieve, integrity, validate
):
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
                if (
                    platform_filter is not None
                    and platform != platform_filter
                    and platform != "source"
                ):
                    print("  -> Skipping platform: " + platform)
                    continue

                if not "relative_path" in manifest[component][platform]:
                    for variant in manifest[component][platform].keys():
                        if cuda_filter is not None and variant != cuda_filter:
                            print("  -> Skipping variant: " + variant)
                            continue

                        parse_artifact(
                            parent,
                            manifest,
                            component,
                            platform,
                            retrieve,
                            integrity,
                            validate,
                            variant,
                        )
                else:
                    parse_artifact(
                        parent, manifest, component, platform, retrieve, integrity, validate
                    )


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
                # print(platform, binTag)
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
                fix_permissions(topdir)

                if collapse:
                    flatdir = os.path.join(output_dir, platform)
                    flatten_tree(topdir, flatdir, binTag)
                    print("  -> Flattened: " + flatdir + "/")

            # Zip files
            elif re.search(r"\.zip", archive):
                print(":: zip: " + archive)
                with zipfile.ZipFile(archive) as zippy:
                    topdir = os.path.commonprefix(zippy.namelist())
                    zippy.extractall()
                zippy.close()

                print("  -> Extracted: " + topdir)
                fix_permissions(topdir)

                if collapse:
                    flatdir = os.path.join(output_dir, platform)
                    flatten_tree(topdir, flatdir, binTag)
                    print("  -> Flattened: " + flatdir + "/")

    print("\nOutput: " + output_dir + "/")
    for item in sorted(os.listdir(output_dir)):
        if os.path.isdir(os.path.join(output_dir, item)):
            print(" - " + item + "/")
        elif os.path.isfile(os.path.join(output_dir, item)):
            print(" - " + item)


def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser()
    # Input options
    parser_group = parser.add_mutually_exclusive_group(required=False)
    parser_group.add_argument("-u", "--url", dest="url", help="URL to manifest")
    parser_group.add_argument("-l", "--label", dest="label", help="Release label version")
    parser.add_argument("-p", "--product", dest="product", help="Product name")
    parser.add_argument("-o", "--output", dest="output", help="Output directory")
    parser.add_argument(
        "--channel",
        dest="channel",
        help="Discover a version from a Repo Channels CDN channel and verify its CAS manifest",
    )
    parser.add_argument(
        "--list",
        dest="list",
        action="store_true",
        help="List channels/products/versions discoverable on the Repo Channels CDN",
    )
    # Filter options
    parser.add_argument("--component", dest="component", help="Component name")
    parser.add_argument("--os", dest="os", help="Operating System")
    parser.add_argument("--arch", dest="arch", help="Architecture")
    parser.add_argument("--variant", dest="cuda", help="Variant")
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
        "-b",
        "--bytes",
        dest="integrity",
        action="store_true",
        help="Verify file size in bytes",
        default=True,
    )
    parser.add_argument(
        "-B",
        "--no-bytes",
        dest="integrity",
        action="store_false",
        help="Skip file size validation",
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

    if args.cuda is not None:
        cuda = args.cuda
    else:
        cuda = None

    if args.output is not None:
        output_dir = args.output
    else:
        output_dir = "flat"

    # Discovery listing mode (Repo Channels CDN); nothing to download
    if args.list:
        list_channels(CHANNELS_DOMAIN, args.product)
        return

    # Content-addressed manifest expectations, set when discovering a channel
    manifest_sha256 = None
    manifest_size = None

    # Get the manifest from --channel discovery (CDN), --url, or --label (legacy)
    if args.channel is not None:
        if args.url is not None:
            err("--channel and --url are mutually exclusive")
        if args.product is None:
            err("Must pass --product argument with --channel")
        manifest_uri, manifest_sha256, manifest_size = discover_release(
            CHANNELS_DOMAIN, args.product, args.channel, args.label
        )
    elif args.url is not None:
        manifest_uri = args.url
    elif args.label is not None:
        if args.product is not None:
            manifest_uri = f"{DOMAIN}/compute/{args.product}/redist/redistrib_{args.label}.json"
        else:
            err("Must pass --product argument")
    else:
        err("Must set an input using --url, --label (with --product), or --channel")

    if args.retrieve is not None:
        retrieve = args.retrieve
    else:
        retrieve = True

    if args.integrity is not None:
        integrity = args.integrity
    else:
        integrity = True

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

    # Read the manifest bytes (local or remote)
    if os.path.isfile(manifest_uri):
        with open(manifest_uri, "rb") as f:
            manifest_bytes = f.read()
    else:
        try:
            manifest_bytes = urlopen(manifest_uri, timeout=TIMEOUT).read()
        except OSError:
            err("redistrib JSON manifest file not found")

    # Verify the content-addressed manifest against releases.json (CAS)
    if manifest_size is not None and len(manifest_bytes) != int(manifest_size):
        err("manifest size mismatch: " + str(len(manifest_bytes)) + " != " + str(manifest_size))
    if manifest_sha256 is not None:
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        if digest != manifest_sha256:
            err("manifest sha256 mismatch:\n  -> Calculation: " + digest + "\n  -> Expectation: " + manifest_sha256)
        print("	 Verified manifest sha256: " + digest)

    try:
        manifest = json.loads(manifest_bytes)
    except json.decoder.JSONDecodeError:
        err("invalid redistrib JSON manifest at " + manifest_uri)

    print(":: Parsing JSON: " + manifest_uri)

    # Do stuff
    fetch_action(
        os.path.dirname(manifest_uri) + "/",
        manifest,
        component,
        platform,
        cuda,
        retrieve,
        integrity,
        validate,
    )
    if unrolled:
        post_action(output_dir, collapse)

    ### END ###


if __name__ == "__main__":
    main()
