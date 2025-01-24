#!/usr/bin/env bash
#shellcheck disable=SC2016,SC2068,SC2207
# Copyright 2024, NVIDIA Corporation
# SPDX-License-Identifier: MIT

#####################################################
## Sample parser for redistrib JSON manifests
## 1. Downloads each component archive
## 2. Validates SHA256 checksums
## 3. Extracts archives
## 4. Flattens into a collapsed directory structure
## 5. Create new product bundle from flattened directory
#####################################################
dirname=$(dirname "$0")
current=$(readlink -e "$dirname")

# default options
domain="https://developer.download.nvidia.com"
output=$PWD
inputdir=$PWD
bundledir=$current
userask=0

# enable compression
ext=".tar.gz"
GZIP_OPT="-9"
cmd_compress=(pigz --no-time -R "$GZIP_OPT")

# default tools
cmd_http=(curl -s)
cmd_save=(wget --tries=3 -q)
cmd_json=(jq -r)
cmd_size=(du -b)
cmd_hash=(sha256sum)
cmd_unpack=(tar -xJf)
cmd_unzip=(unzip -q -u)
cmd_merged=(cp -RT)
cmd_bundle=(tar --totals -cf)

# default stages
download=1
verifysize=1
verifyhash=1
extraction=1
flattendir=1
makebundle=0

err() { echo "[ERROR] $*" | tr '\n' ' '; echo; exit 1; }

run_cmd() { "$@" || err "Command failed: $*"; }

echo_cmd() { local input="$1"; shift; echo "$input" | "$@" || err "Command failed: echo \$input | $*"; }

if_exists() { if [[ -z $1 ]]; then true; else type -p "$1" >/dev/null; fi; }

depends_check() {
    if_exists ${cmd_http[@]}     || err "dependency ${cmd_http[0]} not found for HTTP access"
    if_exists ${cmd_save[@]}     || err "dependency ${cmd_save[0]} not found for downloading"
    if_exists ${cmd_json[@]}     || err "dependency ${cmd_json[0]} not found for parsing JSON"
    if_exists ${cmd_unpack[@]}   || err "dependency ${cmd_unpack[0]} not found for archive extract"
    if_exists ${cmd_unzip[@]}    || err "dependency ${cmd_unzip[0]} not found for zip extract"
    if_exists ${cmd_merged[@]}   || err "dependency ${cmd_merged[0]} not found for directory flatten"
    if_exists ${cmd_bundle[@]}   || err "dependency ${cmd_bundle[0]} not found for creating bundle"
    if_exists ${cmd_compress[@]} || err "dependency ${cmd_compress[0]} not found for compressing bundle"
}

sanity_check() {
    [[ -n $os ]] && [[ -z $arch ]] && err "Must specify arch to filter by OS"
    [[ -z $os ]] && [[ -n $arch ]] && err "Must specify OS to filter by arch"
    [[ -n $url ]] && [[ -n $product ]] && err "Pass (--url) OR (--product and --label)"
    [[ -n $url ]] && [[ -n $label ]] && err "Pass (--url) OR (--product and --label)"
    [[ -n $product ]] && [[ -z $label ]] && err "Must specify label for product"
    [[ -z $product ]] && [[ -n $label ]] && err "Must specify product for label"
}

wait_input() {
    [[ $userask -eq 1 ]] || return 0

    if [[ $2 == "yes" ]]; then
        read -t 5 -p "[Wait] Continue $1? (Y/n): " -r input
        [[ -z $input ]] && echo
        if [[ $input =~ [Nn] ]]; then exit 1
        else [[ $3 -eq 1 ]] || return 1; fi
    elif [[ $2 == "no" ]]; then
        read -t 5 -p "[Wait] Continue $1? (y/N): " -r input
        [[ -z $input ]] && echo
        if [[ $input =~ [Yy] ]]; then [[ $3 -ne 1 ]] || return 1
        else exit 0; fi
    fi
}

fetch_json() {
    json=$(${cmd_http[@]} "$url")
}

path_finder() {
    directory=$(dirname "$url")
    labels=($(${cmd_http[@]} "$directory/" | sed -e 's|>|\n|g' -e 's|<|\n|g' | grep "^redistrib_" | sort -Vr))

    if [[ $1 == "latest" ]]; then
        label=$(echo "${labels[0]}" | sed -e 's|^redistrib_||' -e 's|\.json$||')
        echo ":: Release Label: $label"
    else
        for json in ${labels[@]}; do
            echo "$json" | sed -e 's|^redistrib_|-> |' -e 's|\.json$||'
        done
    fi
}

download_archive() {
    baseurl=$(dirname "$url")
    filename=$(basename "$1")
    run_cmd mkdir -p "$output"
    run_cmd ${cmd_save[@]} "${baseurl}/$1" -O "${output}/${filename}"
    binarchive="${output}/${filename}"
}

validate_filesize() {
    bytes=$(${cmd_size[@]} "$2" | awk '{print $1}')
    if [[ "$bytes" == "$1" ]]; then
        echo "     Verified size: $bytes"
    else
        echo "  => Mismatch size:"
        echo "     -> Calculation: $bytes"
        echo "     -> Expectation: $1"
    fi
}

validate_checksum() {
    hash=$(${cmd_hash[@]} "$2" | awk '{print $1}')
    if [[ "$hash" == "$1" ]]; then
        echo "     Verified ${cmd_hash[0]}: $hash"
    else
        echo "  => Mismatch ${cmd_hash[0]}:"
        echo "     -> Calculation: $hash"
        echo "     -> Expectation: $1"
    fi
}

fix_permissions() {
    [[ -d "$1" ]] || err "Directory does not exist $1"
    # Add user write permission to read-only files
    chmod -R u+w "$1"
}

extract_archives() {
    unset extractdir
    filename=$(basename "$1")
    topdir="${filename//\-archive.*/\-archive}"
    extractdir="${output}/${topdir}"

    mkdir -p "$output"
    cd "$output" || err "unable to cd to output directory: $output"

    [[ -z ${extracts[*]} ]] && [[ ! -d $topdir ]] && wait_input "extraction" "yes"

    if [[ -d $topdir ]]; then
        echo "     Already exists: $topdir"
    elif [[ $filename =~ \.tar ]]; then
        run_cmd ${cmd_unpack[@]} "$1"
        echo "     Extracted: $topdir"
    elif [[ $filename =~ \.zip ]]; then
        run_cmd ${cmd_unzip[@]} "$1"
        echo "     Extracted: $topdir"
    fi

    fix_permissions "$extractdir"
    extracts+=("$topdir")
    cd - >/dev/null || err "unable to cd to previous directory"
}


flatten_archives() {
    if [[ -n $var ]]; then
        flatdir="flat/${product}/${plat}/${var}"
    else
        flatdir="flat/${product}/${plat}"
    fi

    bigdir="${output}/${flatdir}"
    mkdir -p "$bigdir"
    run_cmd ${cmd_merged[@]} "$extractdir/" "$bigdir/" &&
    echo "     Flattened: ${flatdir}"
}

new_tarball() {
    cd "${output}/flat/${product}" || err "unable to cd to flat directory"
    [[ -d $1 ]] || err "flattened platform $1 not found"
    run_cmd mkdir -p "$bundledir"
    rm -rf "${product}-$1-${label}" || err "unable to remove top-level directory"
    mv "$1" "${product}-$1-${label}" || err "top-level directory rename failed"

    bundlefile="${bundledir}/${product}-$1-${label}${ext}"
    run_cmd ${cmd_bundle[@]} - "${product}-$1-${label}" | ${cmd_compress[@]} > "$bundlefile"

    [[ -f "$bundlefile" ]] || err "archive creation failed"
    echo "[DONE] Wrote: ${bundlefile}"
    cd - >/dev/null || err "unable to cd to previous directory"
}

parse_actions() {
    for key in $(echo_cmd "$object" ${cmd_json[@]} 'keys_unsorted[]'); do
        [[ $key == relative_path ]] && relative_path=$(echo_cmd "$object" ${cmd_json[@]} '.relative_path')
        [[ $key == sha256 ]] && sha256=$(echo_cmd "$object" ${cmd_json[@]} '.sha256')
        [[ $key == md5 ]] && md5=$(echo_cmd "$object" ${cmd_json[@]} '.md5')
        [[ $key == size ]] && size=$(echo_cmd "$object" ${cmd_json[@]} '.size')
    done

    unset binarchive
    [[ -n $relative_path ]] &&
    binarchive=$(basename "$relative_path")

    if [[ -f ${output}/${binarchive} ]]; then
        binarchive="${output}/${binarchive}"
        echo "  -> Found: $binarchive"
    elif [[ -f ${inputdir}/${relative_path} ]]; then
        binarchive="${inputdir}/${relative_path}"
        echo "  -> Found: $binarchive"
    elif [[ $download -eq 1 ]] && [[ ! -f $url ]]; then
        [[ -z ${artifacts[*]} ]] && wait_input "download" "yes"
        echo "  -> Download: $relative_path"
        download_archive "$relative_path"
    else
        echo "  -> Artifact: $binarchive"
    fi

    if [[ $verifysize -eq 1 ]]; then
        if [[ -f $binarchive ]]; then
            validate_filesize "$size" "$binarchive"
        fi
    fi

    if [[ $verifyhash -eq 1 ]]; then
        if [[ -f $binarchive ]] && [[ ${cmd_hash[0]} =~ "sha256" ]]; then
            validate_checksum "$sha256" "$binarchive"
        elif [[ -f $binarchive ]] && [[ ${cmd_hash[0]} =~ "md5" ]]; then
            validate_checksum "$md5" "$binarchive"
        fi
    fi

    artifacts+=("$binarchive")
}

usage() {
    echo "USAGE: $0 (--url= | [--product=] [--label=]) [--input=] [--output=]"
    echo "          [--component=] [--os=] [--arch=] [--variant=]"
    echo "          [-W] [-S] [-X] [-F] [--help]"
    echo
    echo "INPUTS"
    echo " -P, --product PRODUCT  Product name"
    echo " -L, --label LABEL      Release label version"
    echo " -U, --url URL          URL to manifest"
    echo " -A, --ask              Require user input"
    echo
    echo "FILTERS"
    echo " --component COMPONENT  Component name"
    echo " --os OS                Operating System"
    echo " --arch ARCH            Architecture"
    echo " --variant VARIANT      Variant"
    echo
    echo "OPTIONS"
    echo " --list                 Directory list of labels for a given product"
    echo " --latest               Parse highest versioned manifest"
    echo " -W, --no-download      Parse manifest without downloads"
    echo " -B, --no-bytes         Skip size in bytes validation"
    echo " -S, --no-checksum      Skip SHA256 checksum validation"
    echo " -X, --no-extract       Do not extract archives"
    echo " -F, --no-flatten       Do not collapse directories"
    echo " -C, --create           Create bundled tarball"
    echo
    echo "FILE PATHS"
    echo " --input INPUT          Input directory [default: $inputdir]"
    echo " --output OUTPUT        Output directory [default: $output]"
    echo " --bundle BUNDLE        Output bundle to [default: $bundledir]"
    echo
    echo " -h, --help             Print usage"
}

# parameters
while [[ -n $1 ]]; do
    if [[ $1 == -h ]] || [[ $1 == --help ]]; then
        usage
        exit 1
    elif [[ $1 == -A ]] || [[ $1 =~ --ask ]]; then
        userask=1
        echo ":: User Input: required"
    elif [[ $1 == -W ]] || [[ $1 =~ --no-download ]]; then
        download=0
        echo ":: Downloads: disabled"
    elif [[ $1 == -B ]] || [[ $1 =~ --no-bytes ]]; then
        verifysize=0
        echo ":: Verify file size: disabled"
    elif [[ $1 == -S ]] || [[ $1 =~ --no-checksum ]]; then
        verifyhash=0
        echo ":: Verify checksum: disabled"
    elif [[ $1 == -X ]] || [[ $1 =~ --no-extract ]]; then
        extraction=0
        echo ":: Extract archives: disabled"
    elif [[ $1 == -F ]] || [[ $1 =~ --no-flatten ]]; then
        flattendir=0
        echo ":: Collapse directories: disabled"
    elif [[ $1 == -C ]] || [[ $1 =~ --create ]]; then
        makebundle=1
        echo ":: Create bundle: enabled"
    elif [[ $1 =~ --output ]]; then
        output=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Output: $output"
    elif [[ $1 =~ --input ]]; then
        inputdir=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Input: $inputdir"
    elif [[ $1 =~ --bundle ]]; then
        bundledir=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Bundle: $bundledir"
    elif [[ $1 =~ --component ]]; then
        component=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Filter by component: $component"
    elif [[ $1 =~ --os ]]; then
        os=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Filter by OS: $os"
    elif [[ $1 =~ --arch ]]; then
        arch=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Filter by architecture: $arch"
    elif [[ $1 =~ --variant ]]; then
        variant=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Filter by variant: $variant"
    elif [[ $1 =~ --product ]]; then
        product=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Product: $product"
    elif [[ $1 == -P ]]; then
        product="$2"; shift
        echo ":: Product: $product"
    elif [[ $1 =~ --label ]]; then
        label=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Release Label: $label"
    elif [[ $1 == -L ]]; then
        label="$2"; shift
        echo ":: Release Label: $label"
    elif [[ $1 =~ --url ]]; then
        url=$(echo "$1" | awk -F "=" '{print $2}' | awk '{print $1}')
        echo ":: Manifest URL: $url"
    elif [[ $1 == -U ]]; then
        url="$2"; shift
        echo ":: Manifest URL: $url"
    elif [[ $1 =~ --latest ]]; then
        label="latest"
        echo ":: Release Label: latest"
    elif [[ $1 =~ --list ]]; then
        label="__list"
    else
        err "unknown argument $1"
    fi

    shift
done

sanity_check

depends_check

if [[ -n $product ]] && [[ -n $label ]]; then
    url="${domain}/compute/${product}/redist/redistrib_${label}.json"
elif [[ -z $url ]]; then
    err "Must set input JSON using (--url) or (--product and --label) parameters"
fi

if [[ -n $product ]] && [[ $label == "latest" ]]; then
    path_finder "latest"
    url="${directory}/redistrib_${label}.json"
elif [[ -n $product ]] && [[ $label =~ ^_ ]]; then
    echo ":: List release labels"
    path_finder
    exit $?
fi

echo -e "\n:: Parsing JSON: $url"
if [[ ! -f $url ]]; then
    fetch_json "$url"
else
    json=$(cat "$url")
fi

IFS=$'\n'
for cmp in $(echo_cmd "$json" ${cmd_json[@]} 'keys_unsorted[]'); do
    unset variants
    [[ $cmp == release_date ]] && published=$(echo_cmd "$json" ${cmd_json[@]} '.release_date') && continue
    [[ $cmp == release_label ]] && label=$(echo_cmd "$json" ${cmd_json[@]} '.release_label') && continue
    [[ $cmp == release_product ]] && product=$(echo_cmd "$json" ${cmd_json[@]} '.release_product') && continue
    [[ -n $component ]] && [[ "$cmp" != "$component" ]] && continue
    echo

    platforms=$(echo_cmd "$json" ${cmd_json[@]} --arg cmp "$cmp" '.[$cmp]')
    variants=($(echo_cmd "$platforms" ${cmd_json[@]} 'to_entries[] | select(.key|endswith("_variant")) | .key + .value[]' | sed 's|_variant||'))
    for plat in $(echo_cmd "$platforms" ${cmd_json[@]} 'keys_unsorted[]'); do
        [[ $plat == version ]] && version=$(echo_cmd "$platforms" ${cmd_json[@]} '.version')
        [[ $plat != source ]] && [[ ! $plat =~ - ]] && continue
        [[ $plat != source ]] && [[ -n $os ]] && [[ -n $arch ]] && [[ $plat != ${os}-${arch} ]] && continue
        [[ $plat != source ]] && [[ ! " ${targets[*]} " =~ $plat ]] && targets+=("$plat")

        echo "$cmp [$version] $plat"

        if [[ -n ${variants[*]} ]]; then
            for var in ${variants[@]}; do
                echo "  :: Variant: $var"
                object=$(echo_cmd "$platforms" ${cmd_json[@]} --arg plat "$plat" --arg var "$var" '.[$plat] | .[$var]')
                parse_actions "$var"
            done
         else
            object=$(echo_cmd "$platforms" ${cmd_json[@]} --arg plat "$plat" '.[$plat]')
            parse_actions
        fi
    done

done
echo "---"

echo -e "\n:: Post Actions"
for binarchive in ${artifacts[@]}; do
    if [[ $extraction -eq 1 ]]; then
        echo " -> $binarchive"
        if [[ -f $binarchive ]]; then
            extract_archives "$binarchive"
        fi
    fi

    if [[ $flattendir -eq 1 ]]; then
        if [[ -d $extractdir ]]; then
            flatten_archives
        fi
    fi
done
echo "---"

wait_input "big tarball" "no" $makebundle && makebundle=1

export -f new_tarball run_cmd
if [[ $makebundle -eq 1 ]]; then
    if [[ -d $bigdir ]]; then
        for target in ${targets[@]}; do
            echo -e "\n:: Bundling $target @ $product == $label [$published]"
            new_tarball "$target"
        done
    else
        echo "SKIP bundle, flatten not found"
    fi
fi
