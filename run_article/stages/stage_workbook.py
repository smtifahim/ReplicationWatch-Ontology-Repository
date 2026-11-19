"""Populates the CDBO curation workbook from the pipeline outputs, then adds the Curation_Queue sheet and highlights the cells that need a curator.
Uses cdbo/tools/fill_workbook.py (the project's own filler) and read_workbook.py (the project's validator)."""
import sys
sys.path.insert(0, str(CDBO_DIR_STR := __import__("pathlib").Path(__file__).resolve().parent.parent / "cdbo" / "tools"))
from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from common import *
import fill_workbook, read_workbook
from cdbo_xlsx import KEY_ROW, FIRST_DATA_ROW
import curation_queue as cq


def build_batch(reg, bib, prov, parser, study, claims, ground, merge):
    pub = {**reg, **{k: v for k, v in bib.items() if v is not None}, **prov, **parser}
    st = dict(study); st["Study_ID"] = STUDY_ID
    st["Imaging_Modality_Mapped_Curie"] = json.dumps(ground["study"]["modality"]["curies"])
    out = []
    ver = json.dumps(ground["versions"])
    for i, (c, g, m) in enumerate(zip(claims, ground["claims"], merge["claims"]), 1):
        d = dict(c); d["Claim_ID"] = CLAIM_ID(i); d["Claim_Evidence_Level"] = "Full Text"
        cd, rg, ms = g["condition"], g["region"], g["measure"]
        if cd["status"] == "matched":
            d["Claim_Condition_Mapped"] = f"{cd['label']} ({cd['curie']})"; d["Claim_Condition_Mapped_Curie"] = json.dumps([cd["curie"]])
        else: d["Claim_Condition_Unmappable"] = c["Claim_Condition"]
        if rg["status"] == "matched":
            d["Claim_Region_Mapped"] = f"{rg['label']} ({rg['curie']})"; d["Claim_Region_Mapped_Curie"] = json.dumps([rg["curie"]])
        else: d["Claim_Region_Unmappable"] = c["Claim_Region"]
        if ms["status"] == "matched": d["Claim_Measure_Mapped_Curie"] = json.dumps(ms["curies"])
        else: d["Claim_Measure_Unmappable"] = c["Claim_Measure"]
        if g["laterality"]["curie"]: d["Claim_Laterality_Mapped_Curie"] = json.dumps([g["laterality"]["curie"]])
        d["Claim_Key"] = m["key"]; d["Claim_Key_Complete"] = "Yes" if m["complete"] else "No"
        d["Grounding_Ontology_Versions"] = ver
        out.append(d)
    return [dict(publication=pub, study=st, claims=out)]


def run(reg, bib, prov, parser, study, claims, ground, merge, validation, grounder=None, name="SE-P1_curation_workbook.xlsx"):
    batch = build_batch(reg, bib, prov, parser, study, claims, ground, merge)
    (OUT / "batch.json").write_text(json.dumps(batch, indent=1, ensure_ascii=False), encoding="utf-8")
    ttl, layout, tpl = CDBO_DIR / "cdbo-core-v0.4.1.ttl", CDBO_DIR / "config" / "excel_layout.json", CDBO_DIR / "out" / "cdbo_template.xlsx"
    path = OUT / name
    rc = fill_workbook.fill(str(ttl), str(tpl), batch, str(path), str(layout))
    assert rc == 0
    queue = cq.build(claims, study, reg, bib, ground, validation, merge, grounder)
    wb = load_workbook(path)
    # highlights
    rowof = {}
    for ws in wb.worksheets:
        if ws.title in ("README", "Lists", "Data_Dictionary"): continue
        cols = {ws.cell(KEY_ROW, i).value: i for i in range(1, ws.max_column + 1) if ws.cell(KEY_ROW, i).value}
        ids = {str(ws.cell(r, 1).value): r for r in range(FIRST_DATA_ROW, ws.max_row + 1) if ws.cell(r, 1).value}
        rowof[ws.title] = (cols, ids)
    n_hl = 0
    for item in queue:
        cols, ids = rowof[item["Sheet"]]
        rid = item["Record_ID"]
        # Bibliographic, SciScore, Registry tabs are keyed by Publication_ID; Study tab by Study_ID; Claim tab by Claim_ID
        r = ids.get(rid)
        if r is None: continue
        for fld, kind in item["_hl"]:
            if fld not in cols: continue
            cell = rowof and wb[item["Sheet"]].cell(r, cols[fld])
            cell.fill = PatternFill("solid", fgColor=cq.KIND[kind])
            cell.comment = Comment(f"{item['Queue_ID']} {kind}: {item['Detail'][:300]}", "pipeline")
            n_hl += 1
    # queue sheet
    ws = wb.create_sheet("Curation_Queue", index=len(wb.sheetnames) - 2)
    heads = ["Queue_ID", "Priority", "Issue", "Entity", "Record_ID", "Sheet", "Field_Key", "Value_Seen", "Detail", "Advisory_Candidates", "Status", "Curator_Decision", "Curator_Notes"]
    ws.append(heads)
    for it in queue: ws.append([it[h] for h in heads])
    widths = [9, 9, 18, 12, 11, 24, 26, 34, 70, 60, 10, 22, 30]
    for i, w in enumerate(widths, 1): ws.column_dimensions[chr(64 + i)].width = w
    for c in ws[1]: c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="44546A"); c.alignment = Alignment(wrap_text=True, vertical="center")
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
        row[2].fill = PatternFill("solid", fgColor=cq.KIND[row[2].value])
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
    dv = DataValidation(type="list", formula1='"Open,Resolved,Deferred,Rejected"', allow_blank=False); ws.add_data_validation(dv); dv.add(f"K2:K{ws.max_row}")
    lg = wb.create_sheet("Curation_Legend", index=len(wb.sheetnames) - 2)
    lg.append(["Colour", "Meaning"])
    lg.append(["Orange", "Unmatched: no ontology term by exact label or EXACT synonym. The claim key is incomplete and the record is its own group until a curator maps it."])
    lg.append(["Yellow", "Not looked up: the lookup (RRID, SciScore, Crossref, PubMed, PMC) could not run in this environment. The cell is empty on purpose. Nothing was invented."])
    lg.append(["Blue", "Fallback or review: grounded by the HP fallback, read from the PDF as a fallback, or a schema limit. Check before relying on it."])
    lg.append(["", "Advisory candidates in Curation_Queue are near-matches by token overlap. They are never applied automatically."])
    lg.column_dimensions["A"].width = 12; lg.column_dimensions["B"].width = 130
    for r, k in zip((2, 3, 4), ("Unmatched", "Not looked up", "Fallback or review")): lg.cell(r, 1).fill = PatternFill("solid", fgColor=cq.KIND[k])
    for c in lg[1]: c.font = Font(bold=True)
    wb.save(path)
    # validate with the project's reader (extra sheets are ignored by it)
    recs, errs = read_workbook.read(str(ttl), str(layout), str(path), str(CDBO_DIR / "out"))
    res = dict(path=str(path.name), articles=len(recs), claims=sum(len(r["claims"]) for r in recs), errors=errs, highlighted_cells=n_hl,
               queue_items=len(queue), queue_by_issue={k: sum(1 for x in queue if x["Issue"] == k) for k in cq.KIND},
               queue_by_priority={k: sum(1 for x in queue if x["Priority"] == k) for k in ("High", "Medium", "Low")})
    save_json("stage_workbook.json", res)
    return res, queue


if __name__ == "__main__":
    import stage1_registry as s1, stage3_extract as s3, stage4_validate as s4, stage5_ground as s5, stage5b_merge as s5b
    reg, bib, parser, pt = s1.run(IN / "efd5369b-test.pdf"); c, s, prov = s3.run(); v = s4.run(c, s, pt); g, go = s5.run(c, s); m = s5b.run(c, go)
    res, q = run(reg, bib, prov, parser, s, c, go, m, v); print(json.dumps(res, indent=1))
