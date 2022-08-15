#!/bin/bash

err() { echo "ERROR: $*"; exit 1; }

rpm_metadata() {
    repomd="repodata/repomd.xml"
    echo ">>> createrepo_c -v --database $PWD"
    createrepo_c -v --database "$PWD"
}

if [[ -z $1 ]] || [[ ! -f $1 ]]; then
    err "USAGE: $0 [*.rpm]"
fi

if [[ ! -f "repodata/repomd.xml" ]]; then
    rpm_metadata
fi

### END ###
