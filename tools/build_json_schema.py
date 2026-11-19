#!/usr/bin/env python3
"""Generate JSON Schemas for the two LLM calls from the CDBO ontology.

Usage: python build_json_schema.py ../ontologies/cdbo-core-v0.4.1.ttl out/

Writes:
  study.schema.json   object with one key per LLM-extracted Study field
  claims.schema.json  object {"claims": [ ...one object per atomic claim... ]}

Keys are the skos:altLabel values. Descriptions are dcterms:description.
Enumerated datatypes become $defs. The schemas use only the common subset
(type, description, enum, required, additionalProperties, $defs, $ref), so
they can be passed to structured-output modes that require every property
to be listed in 'required' and additionalProperties to be false. Confirm
against the chosen vendor's validator before relying on this.
"""
import json
import os
import sys
from cdbo_common import Cdbo

XSD_TYPE = {"xsd:string": "string", "xsd:decimal": "number", "xsd:anyURI": "string",
            "xsd:dateTime": "string", "xsd:date": "string", "xsd:gYear": "string"}


def prop_schema(f):
    if f.range_kind == "enum":
        s = {"$ref": f"#/$defs/{f.range_name}"}
        s = {"description": f.description, "$ref": s["$ref"]}
    else:
        s = {"type": XSD_TYPE.get(f.range_name, "string"), "description": f.description}
    return s


def build(o, domain, wrapper):
    fields = o.extracted(domain)
    used_enums = sorted({f.range_name for f in fields if f.range_kind == "enum"})
    obj = {"type": "object",
           "properties": {f.alt: prop_schema(f) for f in fields},
           "required": [f.alt for f in fields],
           "additionalProperties": False}
    defs = {n: {"type": "string", "enum": o.enums[n]} for n in used_enums}
    base = str(o.ontology_iri).rsplit("/", 1)[0]
    if wrapper:
        defs["Claim"] = obj
        schema = {"type": "object",
                  "properties": {"claims": {"type": "array", "items": {"$ref": "#/$defs/Claim"}}},
                  "required": ["claims"], "additionalProperties": False}
        name, title = "claims", "CDBO claims call output"
    else:
        schema, name, title = obj, "study", "CDBO study metadata call output"
    head = {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{base}/{name}.schema.json", "title": title,
            "description": f"Generated from CDBO {o.version}. Do not edit by hand."}
    return name, {**head, **schema, "$defs": defs}


def main(ttl, outdir):
    o = Cdbo(ttl)
    os.makedirs(outdir, exist_ok=True)
    for domain, wrapper in (("Study", False), ("Claim", True)):
        name, schema = build(o, domain, wrapper)
        path = os.path.join(outdir, f"{name}.schema.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        n = len(o.extracted(domain))
        print(f"wrote {path} ({n} fields)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out")
