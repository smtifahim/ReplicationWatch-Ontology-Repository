#!/usr/bin/env python3
"""Round-trip test: sample JSON -> workbook -> JSON, plus negative tests.
Usage: python test_workbook_roundtrip.py ontology.ttl layout.json schema_dir
Uses made-up IDs (prefix TEST-) and the ontology's own examples as values."""
import json, os, shutil, sys, tempfile
from openpyxl import load_workbook
from cdbo_common import Cdbo
from cdbo_xlsx import load_layout, plan, FIRST_DATA_ROW
import build_excel_template, fill_workbook, read_workbook


def sample(o, domain, i):
    out = {}
    for f in o.extracted(domain):
        ex = f.examples[0] if f.examples else "Not Specified"
        out[f.alt] = ex if f.alt != "Claim_Statement" else f"{ex} (case {i})"
    return out


def main(ttl, lay, sch):
    o = Cdbo(ttl); ok = True
    tmp = tempfile.mkdtemp()
    tpl, filled, back = (os.path.join(tmp, n) for n in ("t.xlsx", "f.xlsx", "b.json"))
    build_excel_template.build(ttl, lay, tpl)
    batch = []
    for n in (1, 2):
        claims = []
        for i in ((1, 2, 3) if n == 1 else (1, 2)):
            c = sample(o, "Claim", i); c["Claim_ID"] = f"TEST-C{n}{i}"
            claims.append(c)
        s = sample(o, "Study", n); s["Study_ID"] = f"TEST-S{n}"
        batch.append({"publication": {"Publication_ID": f"TEST-P{n}", "Article_Title": f"Test article {n}",
                                      "SciScore_Total": 5.5, "Content_Hash": "abc123"},
                      "study": s, "claims": claims})
    assert fill_workbook.fill(ttl, tpl, batch, filled, lay) == 0
    recs, errs = read_workbook.read(ttl, lay, filled, sch)
    print("positive: errors =", len(errs)); [print("  ", e) for e in errs]
    ok &= not errs
    same = len(recs) == 2 and all(
        r["publication"]["Publication_ID"] == b["publication"]["Publication_ID"]
        and r["publication"]["Article_Title"] == b["publication"]["Article_Title"]
        and r["publication"]["SciScore_Total"] == 5.5
        and all(r["study"][k] == b["study"][k] for k in b["study"])
        and sorted(c["Claim_ID"] for c in r["claims"]) == sorted(c["Claim_ID"] for c in b["claims"])
        and all(any(all(rc.get(k) == bc[k] for k in bc) for rc in r["claims"]) for bc in b["claims"])
        for r, b in zip(recs, batch))
    print("round-trip equal:", same); ok &= same
    # re-running the filler must not duplicate rows
    twice = os.path.join(tmp, "f2.xlsx")
    fill_workbook.fill(ttl, filled, batch, twice, lay)
    r2, e2 = read_workbook.read(ttl, lay, twice, sch)
    idem = not e2 and sum(len(r["claims"]) for r in r2) == 5
    print("idempotent re-fill:", idem); ok &= idem
    # sorting rows must not matter: reverse the claim rows
    ws_name = "Claim_Record_Metadata"
    wb = load_workbook(filled); ws = wb[ws_name]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=FIRST_DATA_ROW, max_row=ws.max_row)]
    rows = [r for r in rows if any(x is not None for x in r)]
    for k, r in enumerate(reversed(rows)):
        for j, v in enumerate(r, 1):
            ws.cell(FIRST_DATA_ROW + k, j).value = v
    srt = os.path.join(tmp, "sorted.xlsx"); wb.save(srt)
    r3, e3 = read_workbook.read(ttl, lay, srt, sch)
    print("claims sorted in reverse still read:", not e3 and sum(len(r["claims"]) for r in r3) == 5); ok &= not e3
    # negative tests
    plans, _ = plan(o, load_layout(lay)); cp = next(p for p in plans if p.entity == "Claim")
    def mutate(fn, label, expect):
        nonlocal ok
        wb = load_workbook(filled); ws = wb[ws_name]; fn(ws, cp); p = os.path.join(tmp, "m.xlsx"); wb.save(p)
        _, e = read_workbook.read(ttl, lay, p, sch)
        hit = any(expect in x for x in e)
        print(f"negative [{label}]: caught = {hit}"); ok &= hit
    mutate(lambda ws, p: ws.cell(FIRST_DATA_ROW, p.col_index("Claim_Direction")).__setattr__("value", "Went up"), "bad enum", "not in directionType")
    mutate(lambda ws, p: ws.cell(FIRST_DATA_ROW, p.col_index("Claim_Region")).__setattr__("value", None), "empty extracted cell", "empty")
    mutate(lambda ws, p: ws.cell(FIRST_DATA_ROW + 1, p.col_index("Claim_ID")).__setattr__("value", "TEST-C11"), "duplicate claim id", "duplicate")
    mutate(lambda ws, p: ws.cell(FIRST_DATA_ROW, p.col_index("Source_Study_ID")).__setattr__("value", "TEST-S9"), "dangling study link", "not found")
    mutate(lambda ws, p: ws.cell(2, p.col_index("Claim_Region")).__setattr__("value", "Claim_Regon"), "renamed header", "missing")
    shutil.rmtree(tmp)
    print("ALL WORKBOOK CHECKS PASSED" if ok else "WORKBOOK CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
