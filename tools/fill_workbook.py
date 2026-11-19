#!/usr/bin/env python3
"""Write LLM output (and any script-filled values) into the curation workbook.

Usage: python fill_workbook.py ../ontologies/cdbo-core-v0.4.1.ttl config/excel_layout.json template.xlsx batch.json out.xlsx

batch.json is a list of records, one per article:
  {"publication": {"Publication_ID": "...", ...any publication-level keys},
   "study":       {"Study_ID": "...", ...study keys from the study call},
   "claims":      [{"Claim_ID": "...", ...claim keys from the claims call}, ...]}
Each key is routed to its tab by header name. Unknown keys are an error.
Link keys default sensibly: Publication_ID on the study, Source_Study_ID and
Reporting_Publication_ID on claims, Reported_Study_ID on the publication.
Rows are matched on the first identity column, so re-running updates rows
in place instead of duplicating them. A re-run overwrites only the keys it supplies.
"""
import json
import sys
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from cdbo_common import Cdbo
from cdbo_xlsx import FIRST_DATA_ROW, KEY_ROW, load_layout, plan

WRAP_TOP = Alignment(wrap_text=True, vertical="top")


def cell_value(f, v):
    if v is None:
        return None
    if f.range_kind == "datatype" and f.range_name == "xsd:decimal":
        return float(v)
    if f.range_name == "rdf:JSON" and not isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, dict)):
        raise ValueError(f"{f.alt}: expected a string, got {type(v).__name__}")
    return str(v)


class Sheet:
    def __init__(self, ws, p):
        self.ws, self.p = ws, p
        self.cols = {ws.cell(KEY_ROW, i).value: i for i in range(1, ws.max_column + 1) if ws.cell(KEY_ROW, i).value}
        self.id_key = p.columns[0].key
        self.rows = {}
        r = FIRST_DATA_ROW
        while ws.cell(r, self.cols[self.id_key]).value not in (None, ""):
            self.rows[str(ws.cell(r, self.cols[self.id_key]).value)] = r
            r += 1
        self.next = r

    def put(self, values, fields):
        key = str(values[self.id_key])
        row = self.rows.get(key)
        if row is None:
            row, self.next = self.next, self.next + 1
            self.rows[key] = row
        for k, v in values.items():
            f = fields[k]
            c = self.ws.cell(row, self.cols[k], cell_value(f, v))
            c.alignment = WRAP_TOP
            if not (f.range_kind == "datatype" and f.range_name == "xsd:decimal"):
                c.number_format = "@"


def fill(ttl, template, batch, out, layout_path):
    o = Cdbo(ttl)
    layout = load_layout(layout_path)
    plans, _ = plan(o, layout)
    wb = load_workbook(template)
    sheets = {p.name: Sheet(wb[p.name], p) for p in plans}
    fields = {f.alt: f for f in o.fields}
    keys_by_entity = {e: {c.key for p in plans if p.entity == e for c in p.columns} for e in layout["identity"]}
    errors = []
    for n, rec in enumerate(batch, 1):
        pub, study, claims = dict(rec["publication"]), dict(rec.get("study") or {}), rec.get("claims") or []
        pid = pub["Publication_ID"]
        if study:
            study.setdefault("Publication_ID", pid)
            pub.setdefault("Reported_Study_ID", study["Study_ID"])
        for label, d, ent in [("publication", pub, "Publication"), ("study", study, "Study")] + \
                [(f"claim {i+1}", c, "Claim") for i, c in enumerate(claims)]:
            if ent == "Claim":
                d.setdefault("Source_Study_ID", study.get("Study_ID"))
                d.setdefault("Reporting_Publication_ID", pid)
            for k in d:
                if k not in keys_by_entity[ent]:
                    errors.append(f"record {n} {label}: key '{k}' does not belong to {ent}")
        if errors:
            continue
        for p in plans:
            data = pub if p.entity == "Publication" else study if p.entity == "Study" else None
            if p.entity == "Claim":
                for c in claims:
                    sheets[p.name].put({k: v for k, v in c.items() if k in sheets[p.name].cols and v is not None}, fields)
            elif data:
                sheets[p.name].put({k: v for k, v in data.items() if k in sheets[p.name].cols and v is not None}, fields)
    if errors:
        print("\n".join("ERROR " + e for e in errors)); return 1
    wb.save(out)
    print(f"wrote {out}: {len(batch)} article(s), " +
          ", ".join(f"{p.name}={len(sheets[p.name].rows)} rows" for p in plans))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit("usage: fill_workbook.py ontology.ttl layout.json template.xlsx batch.json out.xlsx")
    ttl, lay, tpl, batch, out = sys.argv[1:]
    sys.exit(fill(ttl, tpl, json.load(open(batch, encoding="utf-8")), out, lay))
