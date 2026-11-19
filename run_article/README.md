# ClaimsDB pipeline, one-article run (SE-P1)

Runs a PDF through: registry, text, LLM extraction (saved output), validation gates, grounding, claim merge, curation workbook, ClaimsDB graph (Turtle-star), claim comparator edges (Excel).

    pip install pyoxigraph==0.4.11 openpyxl rdflib jsonschema     # plus poppler-utils for pdftotext
    bash ont/fetch_ontologies.sh                                  # UBERON, MONDO, HP (not pinned; hashes are logged)
    python run_pipeline.py inputs/efd5369b-test.pdf

| Stage | File |
| --- | --- |
| 1 and 2 registry, text | stages/stage1_registry.py |
| 3 extraction (loads inputs/claims_out.json and study_out.json) | stages/stage3_extract.py |
| 4 validation gates | stages/stage4_validate.py |
| 5 grounding | stages/stage5_ground.py, stages/obo.py |
| 5b claim key and groups (stored CSDO query, pass 1) | stages/stage5b_merge.py |
| curation workbook and queue | stages/stage_workbook.py, stages/curation_queue.py |
| 6 ClaimsDB graph and TTL | stages/stage6_claimsdb.py |
| 7 and 8 edges (stored CSDO query, pass 2), Excel export, portal read | stages/stage7_comparator.py |

cdbo/ is the ontology bundle subset the run needs (CDBO 0.4.1, CSDO 0.1.0, template, schemas, tools, stored queries).

Honest limits of the reported run: the two LLM calls were run in a Claude session, not through the API (stage3 loads their saved JSON; an API call would replace it);
pdftotext replaced Docling; a small exact-match OBO loader replaced OAK; Crossref, PubMed, PMC, RRID, SciScore, BioPortal and InterLex were unreachable,
so those fields are empty and listed in the Curation_Queue tab. No curator decision was applied.
