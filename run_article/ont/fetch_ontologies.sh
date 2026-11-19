#!/usr/bin/env bash
# Downloads the OBO files the grounding stage reads. The files used in the reported run were not pinned releases:
# their sha256 values are recorded in out/stage5_grounding.json. For a reproducible run, pin a release and record its date.
set -e
cd "$(dirname "$0")"
curl -L -o uberon-edit.obo  http://purl.obolibrary.org/obo/uberon.obo
curl -L -o mondo-edit.obo   http://purl.obolibrary.org/obo/mondo.obo
curl -L -o hp.obo           http://purl.obolibrary.org/obo/hp.obo
