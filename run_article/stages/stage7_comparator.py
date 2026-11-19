"""Stages 7 and 8: Claim Comparator and a Portal read.
Reads the RDF-star edges that the CSDO load query (pass 2) produced in the ClaimsDB graph and writes them to an Excel file for the comparator:
one wide sheet for people (Edges), one long sheet that is the RDF-star triple table (Edge_Annotations), and the Groups.
The edge says 'experts should compare these two groups'. It never says one confirms or refutes the other. The 'Candidate_Micropub_Relation'
column is a suggestion for the comparator display, computed here, and is not written to the graph."""
import re, sys
import pyoxigraph as ox
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from common import *
sys.path.insert(0, str(CDBO_DIR / "csdo"))
from csdo_queries import load_queries, fill
import stage6_claimsdb as s6

PFX = s6.PFX
DIRLABEL = {"Concordant": "same direction", "Opposite": "opposite directions", "NullVsEffect": "one reports an effect, the other reports none", "NotComparable": "difference vs association"}


def candidate_micropub(lat, mea, dirrel):
    if dirrel == "NotComparable": return "none", "difference and association claims are not comparable"
    if lat != "Same" or mea != "Same":
        return "none", f"laterality is {lat} and measure is {mea}; both must be Same before a supports or challenges reading is suggested"
    if dirrel == "Concordant": return "mp:supports (candidate)", "same laterality, same measure, same direction"
    return "mp:challenges (candidate)", "same laterality, same measure, " + DIRLABEL[dirrel]


def run_queries(st, groups_meta):
    edges = []
    q = PFX + """SELECT ?a ?b ?l ?m ?d ?v ?cs WHERE { ?a csdo:comparableTo ?b .
        << ?a csdo:comparableTo ?b >> csdo:criteriaSet ?cs ; csdo:lateralityRelation ?l ; csdo:measureRelation ?m ; csdo:directionRelation ?d ; csdo:computedWithVersions ?v }"""
    for r in st.query(q):
        edges.append(dict(a=r["a"].value, b=r["b"].value, lat=r["l"].value, mea=r["m"].value, dir=r["d"].value, ver=r["v"].value, cs=r["cs"].value))
    edges.sort(key=lambda e: tuple(sorted((groups_meta[e["a"]]["name"], groups_meta[e["b"]]["name"]))))
    queries = load_queries(CDBO_DIR / "csdo-core-v0.1.ttl")
    buckets = [dict(cond=str(r["cond"].value), reg=str(r["reg"].value), groups=int(r["groups"].value), edges=int(float(r["edges"].value)))
               for r in st.query(PFX + (CDBO_DIR / "csdo" / "queries" / "load_report_buckets.rq").read_text())]
    return edges, buckets, queries


def portal(st, queries, focus_iri, groups_meta):
    """Stage 8 read for one focus group: neighbours (two criteria sets), broader-region groups, support by facet. Uses the stored portal queries."""
    out = {}
    qdir = CDBO_DIR / "csdo" / "queries"
    pre = PFX
    for cs in ("csdo:DefaultAnchor", "csdo:AnchorPlusMeasure"):
        txt = fill((qdir / "portal_neighbours.rq").read_text(), FOCUS=f"<{focus_iri}>", CRITERIA_SET=cs)
        res = list(st.query(pre + txt))
        others = sorted({t.subject.object.value for t in res if isinstance(t.subject, ox.Triple)})
        out[f"neighbours_{cs.split(':')[1]}"] = sorted(groups_meta[o]["name"] for o in others if o in groups_meta)
    br = list(st.query(pre + fill((qdir / "portal_broader_region.rq").read_text(), FOCUS=f"<{focus_iri}>")))
    out["broader_region_groups"] = [groups_meta[r["other"].value]["name"] for r in br if r["other"].value in groups_meta]
    gm = list(st.query(pre + fill((qdir / "portal_group_members.rq").read_text(), GROUPS=f"<{focus_iri}>")))
    out["support_by_facet"] = [dict(age=r["ageGroup"].value, evidence=r["evidenceLevel"].value, claims=int(r["claims"].value)) for r in gm]
    return out


def style_header(ws, widths):
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="44546A"); c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, w in enumerate(widths, 1): ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions


def run(st, claims, ground, merge, grounder, name="SE-P1_rdfstar_edges_for_comparator.xlsx"):
    cl = {CLAIM_ID(i): c for i, c in enumerate(claims, 1)}
    gr = {g["id"]: g for g in ground["claims"]}
    mk = {m["id"]: m for m in merge["claims"]}
    gmeta = {}
    for g in merge["groups"]:
        ids = g["claims"]; m = mk[ids[0]]
        gmeta[g["iri"]] = dict(name=g["name"], claims=ids, key=m["key"], complete=m["complete"], cond=m["cond"], reg=m["reg"], lat=m["lat"], mea=m["mea"], dir=m["dir"])
    edges, buckets, queries = run_queries(st, gmeta)
    lab = lambda c: f"{grounder.label(c)} ({c})" if c else ""
    wb = Workbook()
    ws = wb.active; ws.title = "README"
    for r in [["RDF-star edges for the Claim Comparator, one article (" + PUB_ID + ")"], [],
              ["What this file is", "A table view of the comparableTo edges in the ClaimsDB graph (SE-P1_claimsdb.ttl). The Turtle-star file is authoritative; this workbook is how the comparator and reviewers can read, filter and load the same edges without an RDF-star store."],
              ["Edges", "One row per edge, for people. Both groups' claims, statements, laterality, measure, direction, sample and p-value are shown side by side."],
              ["Edge_Annotations", "The RDF-star table. Each edge has 6 rows: the plain asserted edge, then the 5 annotations whose subject is the quoted triple << group_A csdo:comparableTo group_B >> (criteriaSet, lateralityRelation, measureRelation, directionRelation, computedWithVersions). Column Turtle_Star re-creates the line. Group by Edge_ID and pivot Annotation_Predicate to get one row per edge. To load into a property-graph or relational comparator, use Quoted_Subject, Quoted_Object as the edge ends and the five annotations as edge properties."],
              ["Groups", "Every Claim Group, whether or not it is in an edge, with the reason it has no edge."],
              ["Reading an edge", "An edge means 'experts should compare these two groups'. It does not say that one confirms or refutes the other. Pairs are stored once, in IRI order (the A side is not a primary side)."],
              ["Candidate_Micropub_Relation", "Computed by the exporter for the comparator display: supports or challenges is suggested only when laterality and measure are both Same. It is NOT stored in the graph."],
              ["Anchor", "Default criteria set: same grounded condition and same grounded region (csdo:DefaultAnchor)."],
              ["Limits of this one-article run", "All claims come from one publication and one cohort (ABCD), so every edge is within-study and not independent evidence. Population qualifiers (monolingual or bilingual) are not part of the anchor and are shown in the Edges sheet so a reviewer can see them."]]:
        ws.append(r)
    ws.column_dimensions["A"].width = 30; ws.column_dimensions["B"].width = 140
    for row in ws.iter_rows():
        for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
    ws["A1"].font = Font(bold=True, size=13)
    for r in range(3, 12): ws.cell(r, 1).font = Font(bold=True)

    we = wb.create_sheet("Edges")
    head = ["Edge_ID", "Group_A", "Group_B", "Anchor_Condition", "Anchor_Region", "Criteria_Set", "Laterality_Relation", "Measure_Relation", "Direction_Relation", "Candidate_Micropub_Relation", "Why_Candidate",
            "A_Claims", "A_Laterality", "A_Measure", "A_Direction", "A_Statement", "A_Source_Reference", "A_P_Value", "A_Sample", "A_Population_Qualifiers",
            "B_Claims", "B_Laterality", "B_Measure", "B_Direction", "B_Statement", "B_Source_Reference", "B_P_Value", "B_Sample", "B_Population_Qualifiers",
            "Same_Publication", "Computed_With_Versions", "Group_A_IRI", "Group_B_IRI"]
    we.append(head)
    wa = wb.create_sheet("Edge_Annotations")
    wa.append(["Edge_ID", "Row_Type", "Quoted_Subject", "Quoted_Predicate", "Quoted_Object", "Annotation_Predicate", "Annotation_Value", "Value_Kind", "Turtle_Star"])
    edge_rows = []
    for n, e in enumerate(edges, 1):
        eid = f"E{n:02d}"; A, B = gmeta[e["a"]], gmeta[e["b"]]
        cand, why = candidate_micropub(e["lat"], e["mea"], e["dir"])
        def side(g):
            cs = [cl[i] for i in g["claims"]]
            j = lambda k: " | ".join(dict.fromkeys(c[k] for c in cs))
            mea = " + ".join(grounder.label(x) or x for x in (g["mea"] or []))
            return [", ".join(g["claims"]), g["lat"], mea, g["dir"], " || ".join(f"{i}: {cl[i]['Claim_Statement']}" for i in g["claims"]), j("Claim_Source_Reference"), j("Claim_P_Value"), j("Claim_Sample_Size"), j("Claim_Population_Qualifiers")]
        we.append([eid, A["name"], B["name"], lab(A["cond"]), lab(A["reg"]), e["cs"].replace(CSDO_NS, "csdo:"), e["lat"], e["mea"], e["dir"], cand, why] + side(A) + side(B) + ["Yes", e["ver"], e["a"], e["b"]])
        qa = f"<< {s6.compact(e['a'])} csdo:comparableTo {s6.compact(e['b'])} >>"
        wa.append([eid, "plain edge (asserted)", s6.compact(e["a"]), "csdo:comparableTo", s6.compact(e["b"]), "", "", "", f"{s6.compact(e['a'])} csdo:comparableTo {s6.compact(e['b'])} ."])
        for ap, av, kind in (("csdo:criteriaSet", e["cs"].replace(CSDO_NS, "csdo:"), "IRI"), ("csdo:lateralityRelation", e["lat"], "literal"), ("csdo:measureRelation", e["mea"], "literal"),
                             ("csdo:directionRelation", e["dir"], "literal"), ("csdo:computedWithVersions", e["ver"], "literal")):
            val = av if kind == "IRI" else f'"{av}"'
            wa.append([eid, "annotation on quoted triple", s6.compact(e["a"]), "csdo:comparableTo", s6.compact(e["b"]), ap, av, kind, f"{qa} {ap} {val} ."])
        edge_rows.append(dict(id=eid, a=A["name"], b=B["name"], lat=e["lat"], mea=e["mea"], dir=e["dir"], cand=cand, why=why, a_claims=A["claims"], b_claims=B["claims"], region=lab(A["reg"])))
    style_header(we, [8, 9, 9, 30, 30, 18, 12, 12, 16, 22, 40] + [14, 10, 26, 13, 60, 12, 24, 30, 40] * 2 + [10, 30, 50, 50])
    style_header(wa, [8, 24, 52, 20, 52, 26, 40, 10, 150])
    inedge = {x for e in edges for x in (e["a"], e["b"])}
    size = {(b["cond"], b["reg"]): b["groups"] for b in buckets}
    wg = wb.create_sheet("Groups")
    wg.append(["Group", "Complete_Key", "In_An_Edge", "Why_No_Edge", "Condition", "Region", "Laterality", "Measure", "Direction", "Claims", "Statement", "Claim_Key", "Group_IRI"])
    for g, m in sorted(gmeta.items(), key=lambda kv: kv[1]["name"]):
        why = ""
        if g not in inedge:
            if not m["reg"]: why = "region not grounded, so the default anchor (condition + region) cannot form"
            elif size.get((obo_iri(m["cond"]), obo_iri(m["reg"])), 1) == 1: why = "alone under its anchor (no other group with the same condition and region)"
            else: why = "other groups share the anchor but pair was not produced; check"
        wg.append([m["name"], "Yes" if m["complete"] else "No", "Yes" if g in inedge else "No", why, lab(m["cond"]), lab(m["reg"]) or "(not grounded)", m["lat"],
                   " + ".join(grounder.label(x) or x for x in (m["mea"] or [])), m["dir"], ", ".join(m["claims"]), " || ".join(cl[i]["Claim_Statement"] for i in m["claims"]), m["key"], g])
    style_header(wg, [8, 10, 10, 50, 28, 32, 11, 30, 14, 12, 70, 52, 50])
    wb.save(OUT / name)
    focus = next(g for g, m in gmeta.items() if "SE-C09" in m["claims"])
    por = portal(st, queries, focus, gmeta)
    por["focus"] = gmeta[focus]["name"]
    info = dict(xlsx=name, edges=edge_rows, n_edges=len(edges), n_annotation_rows=wa.max_row - 1, buckets=buckets,
                groups_in_edges=len(inedge), groups_total=len(gmeta), portal=por)
    save_json("stage7_comparator.json", info)
    return info


if __name__ == "__main__":
    import stage1_registry as s1, stage3_extract as s3, stage4_validate as s4, stage5_ground as s5, stage5b_merge as s5b
    reg, bib, parser, pt = s1.run(IN / "efd5369b-test.pdf"); c, s, prov = s3.run(); v = s4.run(c, s, pt); g, go = s5.run(c, s); m = s5b.run(c, go)
    st, _ = s6.run(reg, bib, prov, parser, s, c, go, m, g)
    print(json.dumps(run(st, c, go, m, g), indent=1)[:3500])
