# build-system-archive-import-examples

[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT-license)
[![Contributing](https://img.shields.io/badge/Contributing-Developer%20Certificate%20of%20Origin-violet)](https://developercertificate.org)


## Overview

Examples for importing precompiled binary `tarball` and `zip` archives into various CI/CD build and packaging systems


## Redistrib JSON

Sample scripts for parsing `redistrib_${label}.json` manifests ([JSON schema](https://developer.download.nvidia.com/compute/redist/redistrib-v2.schema.json)).

  - Downloads each archive
  - Validates SHA256 checksums
  - Extracts archives
  - Flattens into a collapsed directory structure

### Python Usage

```shell
usage: parse_redist.py (-u URL | [-l LABEL] [-p PRODUCT]) [-o OUTPUT]
       option filters: [--component COMPONENT] ([--os OS] [--arch ARCH])
       option toggles: [--no-download] [--no-checksum] [--no-extract] [--no-flatten]
```
> note: for this reference script, Python 3.8 or later is required


#### Example (python)

```shell
python3 ./parse_redist.py --product cuda --label 11.4.2
```

or equivalent

```shell
python3 ./parse_redist.py --url https://developer.download.nvidia.com/compute/cuda/redist/redistrib_11.4.2.json
```

### BASH Usage

```shell
USAGE: ./shell-parse.sh (--url= | [--product=] [--label=]) [--input=] [--output=]
          [--component=] [--os=] [--arch=] [--variant=]
          [-W] [-S] [-X] [-F] [--list] [--latest] [--help]
```
> note: for this reference script, `jq`, `curl`, `wget`, etc. are required


#### Example (bash)

```shell
./shell-parse.sh --product=cuda --label=12.8.0
```

or equivalent

```shell
./shell-parse.sh --product=cuda --latest
```


## CMake

### FindCUDAToolkit

See example [cmake/1_FindCUDAToolkit/](cmake/1_FindCUDAToolkit/)

### ExternalProject

See example [cmake/2_ExternalProject/](cmake/2_ExternalProject/)

## Bazel

### pkg_tar

See example [bazel/1_pkg_tar/](bazel/1_pkg_tar/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)
