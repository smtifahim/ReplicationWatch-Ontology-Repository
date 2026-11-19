"""Stage 6: ClaimsDB. Writes the publication, study and claim records, the grounded ontology terms with labels and ancestors,
the Claim Groups (CSDO load query, pass 1) and the RDF-star comparison edges (pass 2), into one graph and serialises it as Turtle-star.
ClaimsDB is a graph store with relational views; the Turtle-star file is the store content for this one article.
Pass 2 is run by stage 7 through the same function, so the comparator reads exactly what is in this graph."""
import re, sys
import pyoxigraph as ox
from common import *
sys.path.insert(0, str(CDBO_DIR / "csdo"))
from csdo_queries import load_queries
import stage5b_merge as s5b

N, L = ox.NamedNode, ox.Literal
XSD = lambda n: N("http://www.w3.org/2001/XMLSchema#" + n)
RDF_TYPE = N(PREFIXES["rdf"] + "type"); RDFS_LABEL = N(PREFIXES["rdfs"] + "label"); SUBCLASS = N(PREFIXES["rdfs"] + "subClassOf")
OWL_CLASS = N(PREFIXES["owl"] + "Class")
PFX = "".join(f"PREFIX {k}: <{v}> " for k, v in PREFIXES.items()) + "\n"


def literal(vtype, v):
    v = str(v)
    if vtype == "xsd:gYear": return L(v, datatype=XSD("gYear"))
    if vtype == "xsd:anyURI": return L(v, datatype=XSD("anyURI"))
    if vtype == "xsd:decimal": return L(v, datatype=XSD("decimal"))
    if vtype == "xsd:dateTime": return L(v, datatype=XSD("dateTime"))
    if vtype == "rdf:JSON": return L(v, datatype=N(PREFIXES["rdf"] + "JSON"))
    return L(v)


def instance_triples(fields, iri, cls, rec, skip=()):
    out = [ox.Quad(N(iri), RDF_TYPE, N(CDBO_NS + cls), ox.DefaultGraph())]
    for k, v in rec.items():
        if v in (None, "") or k in skip or k not in fields: continue
        f = fields[k]
        p = N(CDBO_NS + f["compact"].split(":", 1)[1])
        out.append(ox.Quad(N(iri), p, literal(f["vtype"], v), ox.DefaultGraph()))
    return out


def build(reg, bib, prov, parser, study, claims, ground, merge, grounder):
    fields = field_table()
    Q = []
    pub = {**reg, **{k: v for k, v in bib.items() if v}, **prov, **parser}
    st = dict(study); st.update(Study_ID=STUDY_ID, Publication_ID=PUB_ID, Imaging_Modality_Mapped_Curie=json.dumps(ground["study"]["modality"]["curies"]))
    Q += instance_triples(fields, ID_NS + "pub/" + PUB_ID, "CDBO_0000001", pub)
    Q += instance_triples(fields, ID_NS + "study/" + STUDY_ID, "CDBO_0000002", st)
    ver = json.dumps(ground["versions"])
    used = set(ground["study"]["modality"]["curies"] or [])
    for i, (c, g, m) in enumerate(zip(claims, ground["claims"], merge["claims"]), 1):
        cid = CLAIM_ID(i); iri = s5b.claim_iri(cid)
        d = dict(c, Claim_ID=cid, Source_Study_ID=STUDY_ID, Reporting_Publication_ID=PUB_ID, Claim_Evidence_Level="Full Text", Claim_Key=m["key"],
                 Claim_Key_Complete="Yes" if m["complete"] else "No", Grounding_Ontology_Versions=ver)
        cd, rg, ms = g["condition"], g["region"], g["measure"]
        if cd["status"] == "matched": d["Claim_Condition_Mapped_Curie"] = json.dumps([cd["curie"]]); used.add(cd["curie"])
        else: d["Claim_Condition_Unmappable"] = c["Claim_Condition"]
        if rg["status"] == "matched": d["Claim_Region_Mapped_Curie"] = json.dumps([rg["curie"]]); used.add(rg["curie"])
        else: d["Claim_Region_Unmappable"] = c["Claim_Region"]
        if ms["status"] == "matched": d["Claim_Measure_Mapped_Curie"] = json.dumps(ms["curies"]); used.update(ms["curies"])
        else: d["Claim_Measure_Unmappable"] = c["Claim_Measure"]
        if g["laterality"]["curie"]: d["Claim_Laterality_Mapped_Curie"] = json.dumps([g["laterality"]["curie"]]); used.add(g["laterality"]["curie"])
        # object-valued mapped fields (the load query reads these IRIs)
        skip = {"Claim_Condition_Mapped", "Claim_Region_Mapped"}
        Q += instance_triples(fields, iri, "CDBO_0000003", d, skip)
        if cd["status"] == "matched": Q.append(ox.Quad(N(iri), N(CDBO_NS + "hasMappedClaimCondition"), N(obo_iri(cd["curie"])), ox.DefaultGraph()))
        if rg["status"] == "matched": Q.append(ox.Quad(N(iri), N(CDBO_NS + "hasMappedClaimRegion"), N(obo_iri(rg["curie"])), ox.DefaultGraph()))
    # ontology terms: label, plus the is_a and part_of closure for OBO terms from the local files
    terms = {}
    for curie in sorted(used):
        pref = curie.split(":")[0]
        onto = {"UBERON": grounder.U, "MONDO": grounder.M, "HP": grounder.H}.get(pref)
        lab = grounder.label(curie)
        if onto:
            allt = {curie} | onto.ancestors(curie)
            for t in allt:
                terms.setdefault(t, (onto.name[t], onto.parents.get(t, set()) & set(onto.name)))
        else:
            terms[curie] = (lab, set())
    for curie, (lab, parents) in terms.items():
        iri = obo_iri(curie) if not curie.startswith("nidm:") else PREFIXES["nidm"] + curie.split(":")[1]
        Q.append(ox.Quad(N(iri), RDF_TYPE, OWL_CLASS, ox.DefaultGraph()))
        if lab: Q.append(ox.Quad(N(iri), RDFS_LABEL, L(lab), ox.DefaultGraph()))
        for p in sorted(parents): Q.append(ox.Quad(N(iri), SUBCLASS, N(obo_iri(p)), ox.DefaultGraph()))
    return Q, terms


def load_store(Q):
    st = ox.Store()
    st.load((CDBO_DIR / "csdo-core-v0.1.ttl").read_bytes(), format=ox.RdfFormat.TURTLE)   # supplies the criteria sets
    n0 = len(st)
    st.extend(Q)
    return st, n0


def run_load(st):
    qs = load_queries(CDBO_DIR / "csdo-core-v0.1.ttl")["load_construct"]
    produced = []
    for text in qs:                       # execution order 1 = groups, 2 = edges
        res = list(st.query(text))
        st.extend([ox.Quad(t.subject, t.predicate, t.object, ox.DefaultGraph()) for t in res])
        produced.append(len(res))
    return produced


# ---------- Turtle-star writer (grouped by subject, readable order) ----------
def compact(iri):
    for k, v in sorted(PREFIXES.items(), key=lambda kv: -len(kv[1])):
        if iri.startswith(v) and re.fullmatch(r"[A-Za-z0-9_\-]+", iri[len(v):]) and not iri[len(v):].endswith("-"):
            return f"{k}:{iri[len(v):]}"
    return f"<{iri}>"


def esc(s): return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def term(t):
    if isinstance(t, ox.NamedNode): return compact(t.value)
    if isinstance(t, ox.Literal):
        if t.language: return f'"{esc(t.value)}"@{t.language}'
        dt = t.datatype.value
        return f'"{esc(t.value)}"' if dt == PREFIXES["xsd"] + "string" else f'"{esc(t.value)}"^^{compact(dt)}'
    if isinstance(t, ox.Triple): return f"<< {term(t.subject)} {term(t.predicate)} {term(t.object)} >>"
    raise ValueError(t)


def category(s):
    if isinstance(s, ox.Triple): return 5, ""
    v = s.value
    for n, pre in ((1, ID_NS + "pub/"), (2, ID_NS + "study/"), (3, ID_NS + "claim/"), (4, CSDO_NS + "group/")):
        if v.startswith(pre): return n, v
    return (6, v) if v.startswith("http://purl.obolibrary.org/obo/") or v.startswith(PREFIXES["nidm"]) else (9, v)


HEAD = {1: "Publication", 2: "Study", 3: "Claim records (CDBO)", 4: "Claim Groups (CSDO) and plain comparableTo edges", 5: "RDF-star edge annotations (quoted triples)", 6: "Grounded ontology terms with labels and subclass closure"}


def write_ttl(st, path, extra_header=""):
    FIELD_ORDER = {f["compact"]: i for i, f in enumerate(field_table().values())}
    by = {}
    for q in st.quads_for_pattern(None, None, None, None):
        by.setdefault(q.subject, []).append((q.predicate, q.object))
    # keep only what this run created: instances, groups, edges, terms (skip the ontology's own axioms)
    keep = {s: po for s, po in by.items() if category(s)[0] < 9}
    ordered = sorted(keep, key=lambda s: (category(s)[0], category(s)[1], term(s)))
    lines = [f"@prefix {k}: <{v}> ." for k, v in PREFIXES.items()] + [""]
    lines += [f"# ClaimsDB content for one article ({PUB_ID}). Turtle-star: quoted triples are written << s p o >>.", extra_header, ""]
    last = None
    for s in ordered:
        cat = category(s)[0]
        if cat != last:
            lines += [f"# ===== {HEAD[cat]} =====", ""]; last = cat
        po = keep[s]
        po.sort(key=lambda x: (0 if x[0] == RDF_TYPE else 1 if x[0] == RDFS_LABEL else 2, term(x[0]), term(x[1])) if cat in (4, 5, 6) else (0 if x[0] == RDF_TYPE else 1, 0, 0))
        if cat in (1, 2, 3):   # records follow the field order of the data dictionary (the workbook column order)
            po.sort(key=lambda x: (0 if x[0] == RDF_TYPE else 1, FIELD_ORDER.get(term(x[0]), 999)))
        lines.append(f"{term(s)}")
        for i, (p, o) in enumerate(po):
            lines.append(f"    {term(p)} {term(o)} " + (";" if i < len(po) - 1 else "."))
        lines.append("")
    Path = __import__("pathlib").Path
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return len(keep)


def run(reg, bib, prov, parser, study, claims, ground, merge, grounder, name="SE-P1_claimsdb.ttl"):
    Q, terms = build(reg, bib, prov, parser, study, claims, ground, merge, grounder)
    st, n0 = load_store(Q)
    produced = run_load(st)
    path = OUT / name
    nsub = write_ttl(st, path, "# Source PDF content hash: " + reg["Content_Hash"])
    # verify the file parses and reproduces the same statements
    chk = ox.Store(); chk.load(path.read_bytes(), format=ox.RdfFormat.TURTLE)
    mine = {q for q in st.quads_for_pattern(None, None, None, None) if category(q.subject)[0] < 9}
    back = set(chk.quads_for_pattern(None, None, None, None))
    # a quoted triple is asserted by the plain edge in this model, so compare on the written set
    ok = mine == back
    info = dict(ttl=name, bytes=path.stat().st_size, subjects=nsub, quads_in_file=len(back), roundtrip_identical=ok, load_query_outputs=produced,
                records=dict(pub=1, study=1, claims=len(claims)), terms=len(terms))
    save_json("stage6_claimsdb.json", info)
    return st, info


if __name__ == "__main__":
    import stage1_registry as s1, stage3_extract as s3, stage4_validate as s4, stage5_ground as s5
    reg, bib, parser, pt = s1.run(IN / "efd5369b-test.pdf"); c, s, prov = s3.run(); v = s4.run(c, s, pt); g, go = s5.run(c, s); m = s5b.run(c, go)
    st, info = run(reg, bib, prov, parser, s, c, go, m, g); print(json.dumps(info, indent=1))
