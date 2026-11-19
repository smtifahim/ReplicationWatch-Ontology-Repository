#!/usr/bin/env python3
"""Checks for the CSDO file. Usage: python lint_csdo.py ../ontologies/csdo-core-v0.1.ttl [../ontologies/cdbo-core-v0.4.1.ttl]
Exit code 1 on any error. Parses every stored query with Oxigraph when pyoxigraph is installed."""
import re
import sys
from collections import Counter
from rdflib import Graph, URIRef, RDF, RDFS, OWL
from rdflib.namespace import SKOS, DCTERMS
from csdo_queries import BASE, fill, load_queries

ALT = re.compile(r"[A-Z][A-Za-z0-9]*(_[A-Za-z0-9]+)*$")


def main(path):
    g = Graph().parse(path, format="turtle")
    errs, warns = [], []
    terms = {s for s in g.subjects() if isinstance(s, URIRef) and str(s).startswith(BASE) and (s, RDF.type, None) in g and (s, RDF.type, RDFS.Datatype) not in g
             and str(s) != BASE + "csdo-core.owl"}
    classes = [s for s in terms if (s, RDF.type, OWL.Class) in g]
    if len(classes) != 2:
        errs.append(f"expected 2 classes, found {len(classes)}")
    alts = Counter(str(g.value(s, SKOS.altLabel)) for s in terms)
    for s in sorted(terms):
        n = str(s)[len(BASE):]
        a = g.value(s, SKOS.altLabel)
        if a is None or not ALT.match(str(a)): errs.append(f"{n}: altLabel missing or not Capitalized_Snake_Case")
        elif alts[str(a)] > 1: errs.append(f"{n}: altLabel '{a}' not unique")
        for p, name in [(RDFS.label, "rdfs:label"), (DCTERMS.description, "dcterms:description")]:
            if g.value(s, p) is None: errs.append(f"{n}: no {name}")
    orders = [int(o) for o in g.objects(None, URIRef(BASE + "hasExecutionOrder"))]
    if len(orders) != len(set(orders)): errs.append("hasExecutionOrder values are not unique")
    q = load_queries(path)
    if len(q["load_construct"]) != 2: errs.append(f"expected 2 load CONSTRUCT queries, found {len(q['load_construct'])}")
    for kind, lst in q.items():
        for text in lst:
            if not text.startswith("PREFIX"): errs.append(f"{kind}: query does not start with its PREFIX declarations")
            if "__VERSIONS__" in text: errs.append(f"{kind}: unreplaced __VERSIONS__")
            if kind.startswith("load") and "{{" in text: errs.append(f"{kind}: load query has a parameter")
            if kind.startswith("portal") and "{{" not in text: warns.append(f"{kind}: portal query without parameters")
    try:
        import pyoxigraph as ox
        st = ox.Store()
        for kind, lst in q.items():
            for text in lst:
                t = fill(text, FOCUS="<http://x/f>", CRITERIA_SET="csdo:DefaultAnchor", GROUPS="<http://x/f>") if "{{" in text else text
                try: list(st.query(t))
                except Exception as e: errs.append(f"{kind}: query does not parse: {str(e)[:100]}")
    except ImportError:
        warns.append("pyoxigraph not installed: queries were not parse-checked")
    if "w3id.org/replicationwatch" in BASE: warns.append("namespace is a placeholder")
    if g.value(None, DCTERMS.license) is None: warns.append("no dcterms:license")
    print(f"CSDO: {len(terms)} terms, {len(classes)} classes, {sum(len(v) for v in q.values())} stored queries")
    for e in errs: print("ERROR", e)
    for w in warns: print("WARN ", w)
    print(f"{len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
