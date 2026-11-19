#!/usr/bin/env python3
"""Three papers, four claims: larger in autism (A), smaller or not larger (B), larger in children but not in adults (C).
Usage: v04/bin/python demo_contradiction.py ../../csdo-core-v0.1.ttl [smaller|notlarger]"""
import os, sys
import pyoxigraph as ox
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from csdo_queries import fill, load_queries
TTL = sys.argv[1]; variant = sys.argv[2] if len(sys.argv) > 2 else "smaller"
Q = load_queries(TTL)
claims = [("A", "P1", "Increased", "Not Specified", "Full Text"),
          ("B", "P2", "Decreased" if variant == "smaller" else "No Difference", "Not Specified", "Full Text"),
          ("C-child", "P3", "Increased", "Child", "Full Text"),
          ("C-adult", "P3", "No Difference", "Adult", "Full Text")]
ttl = ["@prefix cdbo: <https://w3id.org/replicationwatch/cdbo/> . @prefix ex: <http://example.org/> ."]
for i, p, d, age, ev in claims:
    key = f"ASD|Brain|Not Specified|TotalVolume|{d}"
    ttl.append(f'ex:{i} a cdbo:CDBO_0000003 ; cdbo:hasClaimID "{i}" ; cdbo:hasClaimKey "{key}" ; cdbo:hasClaimKeyComplete "Yes" ; cdbo:hasClaimDirection "{d}" ; cdbo:hasClaimAgeGroup "{age}" ; cdbo:hasClaimEvidenceLevel "{ev}" ; cdbo:hasMappedClaimCondition ex:ASD ; cdbo:hasMappedClaimRegion ex:Brain ; cdbo:hasClaimLaterality "Not Specified" ; cdbo:hasMappedClaimMeasureCurie "TotalVolume" .')
s = ox.Store()
s.load(open(TTL, "rb").read(), format=ox.RdfFormat.TURTLE); s.load("\n".join(ttl).encode(), format=ox.RdfFormat.TURTLE)
for text in Q["load_construct"]:
    s.extend([ox.Quad(t.subject, t.predicate, t.object, ox.DefaultGraph()) for t in s.query(text)])
P = "PREFIX cdbo: <https://w3id.org/replicationwatch/cdbo/> PREFIX csdo: <https://w3id.org/replicationwatch/csdo/>\n"
groups = sorted({r["g"].value for r in s.query(P + "SELECT ?g WHERE { ?g a csdo:CSDO_0000001 }")})
members = {}
text = next(q for q in Q["portal_select"] if "GROUPS" in q)
for r in s.query(fill(text, GROUPS=" ".join(f"<{g}>" for g in groups))):
    members.setdefault(r["group"].value, []).append((r["ageGroup"].value, r["claims"].value))
dirs = {r["g"].value: r["d"].value for r in s.query(P + "SELECT ?g ?d WHERE { ?g csdo:hasDirection ?d }")}
names = {g: f"G{i+1}" for i, g in enumerate(sorted(groups, key=lambda g: dirs[g]))}
print(f"--- paper B reports: {claims[1][2]}")
for g in sorted(groups, key=lambda g: names[g]):
    print(f"{names[g]} ({dirs[g]}): " + ", ".join(f"{n} {a}" for a, n in sorted(members[g])))
for r in s.query(P + "SELECT ?a ?b ?d WHERE { << ?a csdo:comparableTo ?b >> csdo:directionRelation ?d }"):
    print(f"edge {names[r['a'].value]} - {names[r['b'].value]}: {r['d'].value}")
