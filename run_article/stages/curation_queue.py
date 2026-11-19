"""Builds the curation queue: every entity the pipeline could not ground, could not look up, or grounded only by fallback.
Nothing in the queue is applied; it is what a curator would see. (The curator-correction step itself is out of scope for this run.)"""
from common import *

ORANGE, YELLOW, BLUE = "F8CBAD", "FFF2CC", "DDEBF7"
KIND = {"Unmatched": ORANGE, "Not looked up": YELLOW, "Fallback or review": BLUE}


def xref_note(conds, grounder):
    if grounder is None: return ""
    cur = [c for (_, c) in conds if c]
    notes = []
    for a in cur:
        for b in cur:
            if a != b and a.startswith("MONDO:"):
                for x, qual in grounder.M.xref.get(a, []):
                    if x == b: notes.append(f"{a} lists {b} as a cross-reference in MONDO {qual}; a cross-reference is not an equivalence, so it is shown but not used.")
    return " ".join(notes)


def build(claims, study, reg, bib, ground, validation, merge, grounder=None):
    q = []
    def add(prio, kind, entity, rid, sheet, field, seen, detail, cands="", highlight=()):
        q.append(dict(Queue_ID=f"Q{len(q)+1:02d}", Priority=prio, Issue=kind, Entity=entity, Record_ID=rid, Sheet=sheet, Field_Key=field,
                      Value_Seen=seen, Detail=detail, Advisory_Candidates=cands, Status="Open", Curator_Decision="", Curator_Notes="", _hl=list(highlight)))
    sug = lambda L: "; ".join(f"{s['curie']} {s['label']} (via '{s['via']}', {s['score']})" for s in L)
    for i, (c, g) in enumerate(zip(claims, ground["claims"]), 1):
        cid = CLAIM_ID(i)
        r = g["region"]
        if r["status"] != "matched":
            add("High", "Unmatched", "Claim", cid, "Claim_Record_Metadata", "Claim_Region", c["Claim_Region"],
                f"No UBERON label or EXACT synonym ({r['status']}). The claim key is incomplete, so this record stays its own group and cannot be compared.",
                sug(r.get("suggestions", [])) or "none found by token overlap",
                [("Claim_Region_Unmappable", "Unmatched"), ("Claim_Region_Mapped", "Unmatched"), ("Claim_Region_Mapped_Curie", "Unmatched")])
        cd = g["condition"]
        if cd["status"] != "matched":
            add("High", "Unmatched", "Claim", cid, "Claim_Record_Metadata", "Claim_Condition", c["Claim_Condition"], "No MONDO or HP exact match.", sug(cd.get("suggestions", [])),
                [("Claim_Condition_Unmappable", "Unmatched"), ("Claim_Condition_Mapped", "Unmatched")])
        m = g["measure"]
        if m["status"] != "matched":
            add("High", "Unmatched", "Claim", cid, "Claim_Record_Metadata", "Claim_Measure", c["Claim_Measure"], "No PATO quality matched by the seed patterns.", "",
                [("Claim_Measure_Unmappable", "Unmatched"), ("Claim_Measure_Mapped_Curie", "Unmatched")])
        if cd["status"] == "matched" and cd["ontology"] == "HP":
            add("Medium", "Fallback or review", "Claim", cid, "Claim_Record_Metadata", "Claim_Condition", c["Claim_Condition"],
                f"MONDO had no exact match; grounded by the HP fallback to {cd['curie']} ({cd['label']}). Check whether MONDO has a usable disease term.", "",
                [("Claim_Condition_Mapped", "Fallback or review")])
    # anchor split across the article
    conds = {}
    for c, g in zip(claims, ground["claims"]):
        conds.setdefault((c["Claim_Condition"], g["condition"].get("curie")), []).append(g["id"])
    if len(conds) > 1:
        add("Medium", "Fallback or review", "Publication", PUB_ID, "Claim_Record_Metadata", "Claim_Condition",
            " | ".join(f"{t} -> {cu}" for (t, cu), _ in conds.items()),
            "The same population is named with different condition strings and they ground to different terms, so the claims never share an anchor. "
            + "; ".join(f"{t}: {', '.join(ids)}" for (t, _), ids in conds.items()),
            "A curator alias (condition string to one term) would unify them. Not applied in this run. " + xref_note(conds, grounder))
    # study level
    for fld, what in (("Analysis_Software_RRID", f"software named: {study['Analysis_Software']}"), ("Study_Dataset_RRID", f"dataset named: {study['Study_Dataset']}")):
        add("Medium", "Not looked up", "Study", STUDY_ID, "Study_Metadata", fld, "", f"RRID resolver not reachable from this environment; {what}.", "", [(fld, "Not looked up")])
    add("Medium", "Fallback or review", "Study", STUDY_ID, "Study_Metadata", "Morphometry_Method", study["Morphometry_Method"],
        "The article uses two methods: voxel-based morphometry for gray matter volume and CAT12 vertex-wise analysis for cortical thickness. The field holds one value per study, so one of the two is lost.",
        "Schema question for the ontology: per-analysis rather than per-study value, or allow a list.", [("Morphometry_Method", "Fallback or review")])
    # publication level
    for fld in ("Pub_Med_Link", "PMC_Link", "Publication_Date"):
        add("Low", "Not looked up", "Publication", PUB_ID, "Bibliographic_Metadata", fld, "", "Crossref, PubMed and PMC lookups are not reachable from this environment.", "", [(fld, "Not looked up")])
    for fld in ("Article_Title", "Listed_Authors", "Publication_Year", "Publication_Venue", "DOI_Link", "Publication_Link"):
        add("Low", "Fallback or review", "Publication", PUB_ID, "Bibliographic_Metadata", fld, bib.get(fld) or "", "Read from the PDF as a fallback. Verify against Crossref when the lookup is available.", "", [(fld, "Fallback or review")])
    add("Low", "Not looked up", "Publication", PUB_ID, "SciScore_Metadata", "SciScore_Total", "", "SciScore API is not reachable from this environment. All SciScore fields are empty. [CONFIRM: FDI LAB]", "",
        [(k, "Not looked up") for k in ("SciScore_Total", "SciScore_Rigor_Subscore", "SciScore_Resources_Subscore", "SciScore_Rigor_Criteria", "SciScore_Detected_Statistical_Tests", "SciScore_Detected_Resources", "SciScore_Supporting_Sentences", "SciScore_Version", "SciScore_Report_Date")])
    # validation warnings
    for v in validation["claims"]:
        if v["reference_empty"]:
            add("Low", "Fallback or review", "Claim", v["id"], "Claim_Record_Metadata", "Claim_Source_Reference", "", "Abstract claim with no table or figure reference. Allowed by the schema; shown for completeness.", "", [])
        if not v["quote_ok"] or not v["p_ok"] or not v["reference_ok"]:
            add("High", "Fallback or review", "Claim", v["id"], "Claim_Record_Metadata", "Claim_Evidence_Quote", "", f"Validation gate failed: quote_ok={v['quote_ok']}, p_ok={v['p_ok']}, reference_ok={v['reference_ok']}", "", [])
    save_json("curation_queue.json", q)
    return q
