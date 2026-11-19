#!/usr/bin/env python3
"""Run the CSDO load and portal queries exactly as stored in the ontology, and check them against an independent
Python implementation of the rules.

Needs pyoxigraph 0.4.x (RDF-star community-group syntax) and rdflib:
    python3 -m venv v04 && v04/bin/pip install pyoxigraph==0.4.11 rdflib
    v04/bin/python run_csdo_flow.py ../../csdo-core-v0.1.ttl
"""
import hashlib, itertools, os, re, sys
import pyoxigraph as ox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from csdo_queries import fill, load_queries

TTL = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
CSDO = "https://w3id.org/replicationwatch/csdo/"; CDBO = "https://w3id.org/replicationwatch/cdbo/"
PFX = f"PREFIX cdbo: <{CDBO}> PREFIX csdo: <{CSDO}> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
Q = load_queries(TTL)
store = ox.Store()
store.load(open(TTL, "rb").read(), format=ox.RdfFormat.TURTLE)       # the ontology itself supplies the criteria sets

def run_load():
    for text in Q["load_construct"]:
        store.extend([ox.Quad(t.subject, t.predicate, t.object, ox.DefaultGraph()) for t in store.query(text)])

def edges():
    r = store.query(PFX + "SELECT ?a ?b ?l ?m ?d ?v WHERE { ?a csdo:comparableTo ?b . << ?a csdo:comparableTo ?b >> csdo:lateralityRelation ?l ; csdo:measureRelation ?m ; csdo:directionRelation ?d ; csdo:computedWithVersions ?v ; csdo:criteriaSet csdo:DefaultAnchor }")
    return {(str(x["a"].value), str(x["b"].value)): (x["l"].value, x["m"].value, x["d"].value) for x in r}, {x["v"].value for x in store.query(PFX + "SELECT ?v WHERE { << ?a csdo:comparableTo ?b >> csdo:computedWithVersions ?v }")}

def records():
    recs = {}
    for x in store.query(PFX + "SELECT ?c ?p ?o WHERE { ?c a cdbo:CDBO_0000003 ; ?p ?o }"):
        recs.setdefault(str(x["c"].value), {})[str(x["p"].value).replace(CDBO, "")] = x["o"].value
    return recs

def groups_of(recs):
    groups = {}
    for c, d in recs.items():
        complete = d["hasClaimKeyComplete"] == "Yes" and "hasClaimKey" in d
        gid = CSDO + "group/" + hashlib.sha1((d["hasClaimKey"] if complete else c).encode()).hexdigest()
        groups.setdefault(gid, {"cond": d.get("hasMappedClaimCondition"), "reg": d.get("hasMappedClaimRegion"), "lat": d.get("hasClaimLaterality"),
            "mea": d.get("hasMappedClaimMeasureCurie"), "dir": d["hasClaimDirection"], "members": []})["members"].append(c)
    return groups

POL = {"Increased": (1, "d"), "Decreased": (-1, "d"), "No Difference": (0, "d"), "Positive Association": (1, "a"), "Negative Association": (-1, "a"), "No Association": (0, "a")}
def relations(ra, rb):
    lat = "Unknown" if ra["lat"] in (None, "Not Specified") or rb["lat"] in (None, "Not Specified") else ("Same" if ra["lat"] == rb["lat"] else "Different")
    mea = "Unknown" if ra["mea"] is None or rb["mea"] is None else ("Same" if ra["mea"] == rb["mea"] else "Different")
    (p1, k1), (p2, k2) = POL[ra["dir"]], POL[rb["dir"]]
    return lat, mea, "NotComparable" if k1 != k2 else "Concordant" if p1 == p2 else "Opposite" if p1 * p2 == -1 else "NullVsEffect"

def oracle(criteria=("cond", "reg"), focus=None):
    G = groups_of(records()); out = {}
    for (a, ra), (b, rb) in itertools.combinations(sorted(G.items()), 2):
        if focus and focus not in (a, b): continue
        if any(ra[k] is None or ra[k] != rb[k] for k in criteria): continue
        out[(a, b)] = relations(ra, rb)
    return out

ok = True
def check(label, cond):
    global ok; print(("PASS " if cond else "FAIL ") + label); ok &= bool(cond)

for b in (1, 2):
    store.load(open(os.path.join(HERE, "data", f"batch{b}.ttl"), "rb").read(), format=ox.RdfFormat.TURTLE)
    run_load()
    e, versions = edges()
    exp = oracle()
    check(f"after batch {b}: {len(e)} edges equal the independent implementation", e == exp)
    if b == 1: e1, n1 = e, len(list(store))
    if b == 1:
        run_load(); check("re-running the load changes nothing (set union)", len(list(store)) == n1)
check("batch 1 edges are unchanged after batch 2", all(edges()[0].get(k) == v for k, v in e1.items()))
check("21 edges from 7 groups sharing the anchor", len(edges()[0]) == 21)
check("edges carry the ontology versions used", edges()[1] == {"CSDO 0.1.0-draft; CDBO 0.4.1-draft"})
check("11 records form 10 groups", len(groups_of(records())) == 10)

focus = CSDO + "group/" + hashlib.sha1(b"ASD|MedSFG|Right|GMV|Increased").hexdigest()
def portal(setname):
    text = fill(Q["portal_construct"][0], FOCUS=f"<{focus}>", CRITERIA_SET=f"csdo:{setname}")
    res = list(store.query(text))
    return {(str(t.subject.subject), str(t.subject.object)): t for t in res if hasattr(t.subject, "predicate")}
check("portal CONSTRUCT, default anchor: 6 neighbours", len(portal("DefaultAnchor")) == 6)
check("portal CONSTRUCT, anchor plus measure: 5 neighbours (the cortical-thickness group drops out)", len(portal("AnchorPlusMeasure")) == 5)
br = list(store.query(PFX + fill(Q["portal_select"][0] if "FOCUS" in Q["portal_select"][0] else Q["portal_select"][1], FOCUS=f"<{focus}>")))
check("broader-region query finds the SFG group (hierarchy at query time)", len(br) == 1 and str(br[0]["otherRegion"].value).endswith("SFG"))
mem = list(store.query(fill(next(q for q in Q["portal_select"] if "GROUPS" in q), GROUPS=f"<{focus}>")))
check("group members split by age group and evidence level (R1 full text, R2 abstract only)", sorted((str(r["evidenceLevel"].value), str(r["claims"].value)) for r in mem) == [("Abstract Only", "1"), ("Full Text", "1")])
cnt = list(store.query(next(q for q in Q["load_report"] if "recordsWithoutAnchor" in q)))[0]
check("load report: 1 record without anchor, 2 incomplete keys", cnt["recordsWithoutAnchor"].value == "1" and cnt["incompleteKeys"].value == "2")
bk = list(store.query(next(q for q in Q["load_report"] if "?groups" in q)))[0]
check("load report: largest anchor has 7 groups and 21 edges", bk["groups"].value == "7" and float(bk["edges"].value) == 21)
print("ALL PASSED" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
