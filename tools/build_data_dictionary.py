#!/usr/bin/env python3
"""Generate the data dictionary (CSV and Markdown) from the CDBO ontology.

Usage: python build_data_dictionary.py ../ontologies/cdbo-core-v0.4.1.ttl out/

One row per field property. 'Field_Key' is the skos:altLabel, the key used in
JSON output, spreadsheet columns and the relational views.
"""
import csv
import os
import sys
from cdbo_common import Cdbo

COLS = ["Field_Key", "Label", "Compact_URI", "Group_Path", "Applies_To", "Value_Type",
        "Allowed_Values", "Role", "Filled_By", "Definition", "Example", "Typical_Sections",
        "Standards_And_Sources"]

FILLED_BY_GROUP = {
    "Registry_Metadata": "Registry script",
    "Bibliographic_Metadata": "Bibliographic lookup (Crossref, PubMed, PMC XML); LLM only as fallback",
    "SciScore_Metadata": "SciScore API (per unique article)",
    "Extraction_Provenance_Metadata": "Pipeline",
}


def filled_by(o, f):
    if f.role == "grouping":
        return "Grouping only"
    if f.role == "extracted":
        return f"LLM {'study' if f.domain == 'Study' else 'claims'} call"
    top = f.path[1] if len(f.path) > 1 else ""
    if top in FILLED_BY_GROUP:
        return FILLED_BY_GROUP[top]
    if f.role == "preprocessing":
        return "Registry script"
    if f.role == "mapping":
        return "Grounding / registration script"
    return "Pipeline script"


def rows(o):
    out = []
    for f in sorted(o.fields, key=lambda x: (x.path, x.name)):
        if f.range_kind == "enum":
            vtype, allowed = f.range_name, "; ".join(o.enums[f.range_name])
        elif f.range_kind == "class":
            vtype, allowed = f"link to {f.range_name}", ""
        else:
            vtype, allowed = f.range_name, ""
        out.append({
            "Field_Key": f.alt, "Label": f.label, "Compact_URI": f.curie,
            "Group_Path": " > ".join(f.path[:-1]), "Applies_To": f.domain,
            "Value_Type": vtype, "Allowed_Values": allowed,
            "Role": f.role, "Filled_By": filled_by(o, f), "Definition": f.description,
            "Example": " | ".join(f.examples), "Typical_Sections": "; ".join(f.sections),
            "Standards_And_Sources": " || ".join(f.citations)})
    return out


def main(ttl, outdir):
    o = Cdbo(ttl)
    os.makedirs(outdir, exist_ok=True)
    data = rows(o)
    csv_path = os.path.join(outdir, "data_dictionary.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(data)
    md_path = os.path.join(outdir, "data_dictionary.md")
    esc = lambda s: s.replace("|", "\\|").replace("\n", " ")
    show = ["Field_Key", "Applies_To", "Value_Type", "Role", "Filled_By", "Definition", "Example"]
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(f"# CDBO data dictionary (ontology version {o.version})\n\n")
        fh.write("Generated from the ontology. Do not edit by hand. The CSV has all columns.\n\n")
        fh.write("| " + " | ".join(show) + " |\n|" + "---|" * len(show) + "\n")
        for r in data:
            if r["Role"] == "grouping":
                continue
            fh.write("| " + " | ".join(esc(r[c]) for c in show) + " |\n")
    print(f"wrote {csv_path} and {md_path} ({len(data)} rows, {sum(r['Role']!='grouping' for r in data)} leaf fields)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out")
