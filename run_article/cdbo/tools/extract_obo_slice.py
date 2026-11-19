#!/usr/bin/env python3
"""Extract a small, versioned slice of an OBO ontology as Turtle.

Usage: python extract_obo_slice.py ontology.obo "PATO:0000918,PATO:0000915" out.ttl "Slice title" source-url commit license-url

Keeps each listed term's label and definition, and the is_a links that stay inside the slice
(parents named in the list). Terms keep their original OBO IRIs (http://purl.obolibrary.org/obo/PATO_0000918).
"""
import sys
from rdflib import Graph, Namespace, RDF, RDFS, OWL, Literal, URIRef
from rdflib.namespace import DCTERMS

IAO_DEF = URIRef("http://purl.obolibrary.org/obo/IAO_0000115")

def read_obo(path):
    out, cur = {}, None
    for line in open(path, encoding="utf8"):
        line = line.rstrip("\n")
        if line == "[Term]":
            cur = {"isa": [], "def": None}
            continue
        if line.startswith("["):
            cur = None
            continue
        if cur is None:
            continue
        if line.startswith("id: "):
            cur["id"] = line[4:]
            out[cur["id"]] = cur
        elif line.startswith("name: "):
            cur["name"] = line[6:]
        elif line.startswith("def: "):
            d = line[5:]
            cur["def"] = d[1:d.index('" ', 1)] if d.startswith('"') and '" ' in d else d.strip('"')
        elif line.startswith("is_a: "):
            cur["isa"].append(line[6:].split(" !")[0].strip())
    return out

def iri(curie):
    pre, loc = curie.split(":")
    return URIRef(f"http://purl.obolibrary.org/obo/{pre}_{loc}")

def main(obo, curies, out, title, source, commit, license_url):
    terms = read_obo(obo)
    want = [c.strip() for c in curies.split(",") if c.strip()]
    g = Graph()
    g.bind("dcterms", DCTERMS); g.bind("owl", OWL); g.bind("obo", Namespace("http://purl.obolibrary.org/obo/")); g.bind("iao", Namespace("http://purl.obolibrary.org/obo/IAO_"))
    ont = URIRef("https://w3id.org/replicationwatch/cdbo/imports/" + out.split("/")[-1].replace(".ttl", ""))
    g.add((ont, RDF.type, OWL.Ontology)); g.add((ont, RDFS.label, Literal(title)))
    g.add((ont, DCTERMS.source, URIRef(source + commit)))
    g.add((ont, DCTERMS.license, URIRef(license_url)))
    g.add((ont, DCTERMS.created, Literal("2026-11-05")))
    for c in want:
        t = terms[c]
        g.add((iri(c), RDF.type, OWL.Class)); g.add((iri(c), RDFS.label, Literal(t["name"], lang="en")))
        if t["def"]:
            g.add((iri(c), IAO_DEF, Literal(t["def"], lang="en")))
        for p in t["isa"]:
            if p in want:
                g.add((iri(c), RDFS.subClassOf, iri(p)))
    g.serialize(out, format="turtle")
    print(f"wrote {out}: {len(want)} terms, {len(g)} triples")

if __name__ == "__main__":
    main(*sys.argv[1:8])
