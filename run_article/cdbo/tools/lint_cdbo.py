#!/usr/bin/env python3
"""Build checks for the ClaimsDB Ontology (CDBO).

Usage: python lint_cdbo.py cdbo-core-v0.3.ttl
Exit code 1 if any ERROR is found. WARN lines are advisory.
"""
import re
import sys
from collections import Counter
from cdbo_common import Cdbo

ALT = re.compile(r"[A-Z][A-Za-z0-9]*(_[A-Za-z0-9]+)*$")
PROMPT_PROP = {"Study": "hasStudyMetadataExtractionPrompt", "Claim": "hasClaimExtractionPrompt"}


def main(path):
    o = Cdbo(path)
    errors, warns = [], []
    E = lambda n, m: errors.append(f"ERROR {n}: {m}")
    W = lambda n, m: warns.append(f"WARN  {n}: {m}")

    alts = Counter(f.alt for f in o.fields)
    for f in o.fields:
        if not f.alt:
            E(f.name, "no skos:altLabel")
        elif not ALT.match(f.alt):
            E(f.name, f"altLabel '{f.alt}' is not Capitalized_Snake_Case")
        if alts[f.alt] > 1:
            E(f.name, f"altLabel '{f.alt}' is not unique")
        if not f.label:
            E(f.name, "no rdfs:label")
        if not f.description:
            E(f.name, "no dcterms:description")
        if f.name != "hasClaimsDBMetadata" and not f.domain:
            E(f.name, "no rdfs:domain")
        if f.parent and f.parent not in o.by_name:
            E(f.name, f"parent {f.parent} is not a declared field property")
        if f.role == "grouping":
            if f.range_kind != "none":
                E(f.name, "a grouping property must not have a range")
        else:
            if f.range_kind == "none":
                E(f.name, "no rdfs:range")
        if f.role == "extracted":
            if not f.examples:
                E(f.name, "extracted field has no IAO:0000112 example")
            if f.range_kind == "enum":
                allowed = o.enums[f.range_name]
                for ex in f.examples:
                    if ex not in allowed:
                        E(f.name, f"example '{ex}' is not in {f.range_name}")
        # prompts
        if f.role == "extracted":
            want = PROMPT_PROP.get(f.domain)
            if f.prompt is None or f.prompt_property != want:
                E(f.name, f"missing prompt on cdbo:{want}")
            else:
                p = f.prompt
                if p.get("field") != f.alt:
                    E(f.name, "prompt 'field' differs from skos:altLabel")
                if p.get("description") != f.description:
                    E(f.name, "prompt 'description' differs from dcterms:description")
                for ex in f.examples:
                    if ex not in p.get("example", ""):
                        E(f.name, "prompt 'example' does not contain the IAO:0000112 example")
                if not p.get("normalization"):
                    E(f.name, "prompt has no 'normalization' rule")
                if f.range_kind == "enum" and p.get("allowed_values") != o.enums[f.range_name]:
                    E(f.name, "prompt 'allowed_values' differs from the datatype")
        elif f.prompt is not None:
            E(f.name, f"{f.role} field carries an extraction prompt")

    # general prompts on the three groups
    for grp, prop in [("hasClaimsDBMetadata", "hasGeneralClaimsDBExtractionPrompt"),
                      ("hasStudyMetadata", "hasGeneralStudyMetadataExtractionPrompt"),
                      ("hasClaimRecordMetadata", "hasGeneralClaimExtractionPrompt")]:
        if o.general_prompt(grp, prop) is None:
            E(grp, f"missing general prompt cdbo:{prop}")

    # enum values unique and non-empty
    for n, vals in o.enums.items():
        if len(vals) != len(set(vals)) or not vals:
            E(n, "enumeration has duplicate or no members")

    # cycle check
    for f in o.fields:
        if len(f.path) > 8:
            E(f.name, "property hierarchy deeper than 8 levels (cycle?)")

    # advisory
    if "w3id.org/replicationwatch" in o.ns:
        W("ontology", "namespace is a placeholder")
    if o.g.value(o.ontology_iri, __import__("rdflib").DCTERMS.license) is None:
        W("ontology", "no dcterms:license on the ontology")
    for n in ("hasClaimStatement", "hasClaimComparator", "hasClaimSlotMetadata"):
        if n in o.by_name and not o.by_name[n].citations:
            W(n, "no dcterms:bibliographicCitation")

    ext = Counter(f.domain for f in o.fields if f.role == "extracted")
    roles = Counter(f.role for f in o.fields)
    print(f"CDBO {o.version}: {len(o.fields)} field properties, {len(o.enums)} enumerations, {len(o.classes)} classes")
    print("roles:", dict(roles))
    print("LLM-extracted fields by domain:", dict(ext))
    for line in errors + warns:
        print(line)
    print(f"{len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "cdbo-core-v0.3.ttl"))
