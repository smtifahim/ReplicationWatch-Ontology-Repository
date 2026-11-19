#!/usr/bin/env python3
"""Check that every CURIE in config/grounding_seed.json exists in the vendored slices.

Usage: python check_grounding_seed.py config/grounding_seed.json imports
"""
import glob, json, sys
from rdflib import Graph, RDFS, URIRef

def main(seed_path, imports_dir):
    g = Graph()
    for f in glob.glob(imports_dir + "/*.ttl"):
        g.parse(f, format="turtle")
    seed = json.load(open(seed_path))
    curies = [v for v in seed["laterality"].values() if v] + [r["curie"] for r in seed["measure_quality"]]
    errors = 0
    for c in curies:
        pre, loc = c.split(":")
        node = URIRef(f"http://purl.obolibrary.org/obo/{pre}_{loc}")
        lab = g.value(node, RDFS.label)
        if lab is None:
            print("MISSING", c); errors += 1
        else:
            print("ok", c, str(lab))
    pats = [p for r in seed["measure_quality"] for p in r["patterns"]]
    dup = {p for p in pats if pats.count(p) > 1}
    if dup:
        print("DUPLICATE PATTERNS", dup); errors += 1
    print(f"{errors} error(s)")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
