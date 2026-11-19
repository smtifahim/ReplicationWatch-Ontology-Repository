#!/usr/bin/env python3
"""Read the curation workbook back into JSON records and validate it.

Usage: python read_workbook.py ontology.ttl layout.json workbook.xlsx out.json [schema_dir]

Checks: ontology version stamp, headers, unique and consistent IDs, enumerated
values, decimals, JSON cells, empty LLM-extracted cells, and (when schema_dir
holds study.schema.json and claims.schema.json) the same JSON Schemas used for
the LLM calls. Exit code 1 if any error is found. Rows are matched by ID, so
sorting and filtering in Excel are safe.
"""
import json
import os
import sys
from collections import defaultdict
from jsonschema import Draft202012Validator
from openpyxl import load_workbook
from cdbo_common import Cdbo
from cdbo_xlsx import FIRST_DATA_ROW, KEY_ROW, load_layout, plan

OPTIONAL_EMPTY = {"Claim_Source_Reference"}


def readme_value(wb, label):
    ws = wb["README"]
    for r in range(1, 12):
        if ws.cell(r, 1).value == label:
            return ws.cell(r, 2).value
    return None


def coerce(f, v, where, errs):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if f.range_kind == "datatype" and f.range_name == "xsd:decimal":
        try:
            return float(v)
        except (TypeError, ValueError):
            errs.append(f"{where}: '{v}' is not a number"); return None
    if f.range_name == "rdf:JSON":
        try:
            return json.loads(v) if isinstance(v, str) else v
        except ValueError:
            errs.append(f"{where}: cell is not valid JSON"); return None
    return str(v)


def read(ttl, layout_path, xlsx, schema_dir=None):
    o = Cdbo(ttl)
    layout = load_layout(layout_path)
    plans, _ = plan(o, layout)
    wb = load_workbook(xlsx, data_only=True)
    errs = []
    v = readme_value(wb, "Ontology version")
    if v != o.version:
        errs.append(f"README: workbook was built for ontology '{v}', loaded ontology is '{o.version}'")
    data = {}          # tab -> {id: {key: value}}
    for p in plans:
        if p.name not in wb.sheetnames:
            errs.append(f"missing tab {p.name}"); continue
        ws = wb[p.name]
        hdr = {ws.cell(KEY_ROW, i).value: i for i in range(1, ws.max_column + 1) if ws.cell(KEY_ROW, i).value}
        want = [c.key for c in p.columns]
        for k in want:
            if k not in hdr:
                errs.append(f"{p.name}: header '{k}' is missing")
        for k in hdr:
            if k not in want:
                errs.append(f"{p.name}: unexpected header '{k}'")
        rows, id_key = {}, want[0]
        for r in range(FIRST_DATA_ROW, ws.max_row + 1):
            vals = {k: ws.cell(r, hdr[k]).value for k in want if k in hdr}
            if all(x in (None, "") for x in vals.values()):
                continue
            where = f"{p.name} row {r}"
            rid = vals.get(id_key)
            if rid in (None, ""):
                errs.append(f"{where}: empty {id_key}"); continue
            rid = str(rid)
            if rid in rows:
                errs.append(f"{where}: duplicate {id_key} '{rid}'"); continue
            rec = {}
            for c in p.columns:
                if c.key not in hdr:
                    continue
                f, raw = c.field, vals[c.key]
                val = coerce(f, raw, f"{where} {c.key}", errs)
                if val is None:
                    if f.role == "extracted" and c.key not in OPTIONAL_EMPTY:
                        errs.append(f"{where} {c.key}: empty (use 'Not Specified')")
                    if c.key in OPTIONAL_EMPTY and f.role == "extracted":
                        rec[c.key] = ""
                    continue
                if f.range_kind == "enum" and val not in o.enums[f.range_name]:
                    errs.append(f"{where} {c.key}: '{val}' is not in {f.range_name}")
                rec[c.key] = val
            rec["_row"] = r
            rows[rid] = rec
        data[p.name] = rows
    # cross-tab identity consistency within each entity
    for ent, ident in layout["identity"].items():
        merged = {}
        for p in [x for x in plans if x.entity == ent]:
            for rid, rec in data.get(p.name, {}).items():
                for k in ident[1:]:
                    val = rec.get(k)
                    if (rid, k) in merged and merged[(rid, k)] != val:
                        errs.append(f"{p.name} row {rec['_row']}: {k} '{val}' disagrees with another tab for {ident[0]} {rid}")
                    merged.setdefault((rid, k), val)
    pub_tabs = [p.name for p in plans if p.entity == "Publication"]
    study_tab = next(p.name for p in plans if p.entity == "Study")
    claim_tab = next(p.name for p in plans if p.entity == "Claim")
    pubs = defaultdict(dict)
    for t in pub_tabs:
        for rid, rec in data.get(t, {}).items():
            pubs[rid].update({k: x for k, x in rec.items() if k != "_row"})
    for rid, rec in data.get(study_tab, {}).items():
        if rec.get("Publication_ID") not in pubs:
            errs.append(f"{study_tab} row {rec['_row']}: Publication_ID '{rec.get('Publication_ID')}' not found in publication tabs")
    for rid, rec in data.get(claim_tab, {}).items():
        if rec.get("Reporting_Publication_ID") not in pubs:
            errs.append(f"{claim_tab} row {rec['_row']}: Reporting_Publication_ID not found in publication tabs")
        if rec.get("Source_Study_ID") not in data.get(study_tab, {}):
            errs.append(f"{claim_tab} row {rec['_row']}: Source_Study_ID '{rec.get('Source_Study_ID')}' not found in {study_tab}")
    # schema validation of the LLM-extracted parts
    if schema_dir:
        sch_s = json.load(open(os.path.join(schema_dir, "study.schema.json")))
        sch_c = json.load(open(os.path.join(schema_dir, "claims.schema.json")))
        vs = Draft202012Validator(sch_s)
        vc = Draft202012Validator({"$ref": "#/$defs/Claim", "$defs": sch_c["$defs"]})
        for rid, rec in data.get(study_tab, {}).items():
            inst = {k: rec[k] for k in sch_s["properties"] if k in rec}
            for e in vs.iter_errors(inst):
                errs.append(f"{study_tab} row {rec['_row']}: schema: {e.message[:120]}")
        for rid, rec in data.get(claim_tab, {}).items():
            inst = {k: rec[k] for k in sch_c["$defs"]["Claim"]["properties"] if k in rec}
            for e in vc.iter_errors(inst):
                errs.append(f"{claim_tab} row {rec['_row']}: schema: {e.message[:120]}")
    records = []
    studies = {r: {k: x for k, x in rec.items() if k != "_row"} for r, rec in data.get(study_tab, {}).items()}
    for pid, pub in pubs.items():
        st = studies.get(pub.get("Reported_Study_ID"), {})
        cl = [{k: x for k, x in rec.items() if k != "_row"} for rec in data.get(claim_tab, {}).values()
              if rec.get("Reporting_Publication_ID") == pid]
        records.append({"publication": pub, "study": st, "claims": cl})
    return records, errs


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: read_workbook.py ontology.ttl layout.json workbook.xlsx out.json [schema_dir]")
    recs, errs = read(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[5] if len(sys.argv) > 5 else None)
    with open(sys.argv[4], "w", encoding="utf-8") as fh:
        json.dump(recs, fh, indent=2, ensure_ascii=False)
    for e in errs:
        print("ERROR", e)
    print(f"{len(recs)} article(s), {sum(len(r['claims']) for r in recs)} claim(s), {len(errs)} error(s)")
    sys.exit(1 if errs else 0)
