#!/usr/bin/env python3
"""Run the ClaimsDB pipeline on one article, from PDF to comparator edges.

    python run_pipeline.py [path/to/article.pdf]

Needs: python 3.11+, pyoxigraph 0.4.x, openpyxl, rdflib, jsonschema, poppler-utils (pdftotext, pdfinfo), and the OBO files in ./ont
(run ont/fetch_ontologies.sh; set ONT_DIR to use another folder). The claims and study JSON from the two LLM calls are read from inputs/.
Outputs go to out/."""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "stages"))
from common import *
import stage1_registry as s1, stage3_extract as s3, stage4_validate as s4, stage5_ground as s5, stage5b_merge as s5b
import stage_workbook as sw, stage6_claimsdb as s6, stage7_comparator as s7

pdf = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else IN / "efd5369b-test.pdf"
T = {}
def tick(n, t0): T[n] = round(time.time() - t0, 2); print(f"[{n}] {T[n]}s")

t = time.time(); reg, bib, parser, pages = s1.run(pdf); tick("1-2 registry and text", t)
t = time.time(); claims, study, prov = s3.run(); tick("3 extraction (load saved LLM output)", t)
t = time.time(); val = s4.run(claims, study, pages); tick("4 validation gates", t)
t = time.time(); grounder, ground = s5.run(claims, study); tick("5 grounding", t)
t = time.time(); merge = s5b.run(claims, ground); tick("5b claim merge", t)
t = time.time(); wbres, queue = sw.run(reg, bib, prov, parser, study, claims, ground, merge, val, grounder); tick("curation workbook", t)
t = time.time(); store, db = s6.run(reg, bib, prov, parser, study, claims, ground, merge, grounder); tick("6 claimsdb", t)
t = time.time(); comp = s7.run(store, claims, ground, merge, grounder); tick("7-8 comparator and portal", t)
save_json("run_summary.json", dict(timings_s=T, article=pdf.name, validation=val["summary"], grounding_versions=ground["versions"], merge=dict(complete=merge["n_complete"], groups=merge["n_groups"]),
                                   workbook=wbres, claimsdb=db, comparator=dict(edges=comp["n_edges"], annotation_rows=comp["n_annotation_rows"], groups_in_edges=comp["groups_in_edges"])))
print("done")
