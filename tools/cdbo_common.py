"""Shared loader for the ClaimsDB Ontology (CDBO).

Reads the Turtle file and returns plain Python structures, so the lint,
JSON Schema, data dictionary and prompt assembly scripts all work from the
same source of truth: the ontology.
"""
import json
from dataclasses import dataclass, field
from rdflib import Graph, RDF, RDFS, OWL, URIRef
from rdflib.collection import Collection
from rdflib.namespace import SKOS, DCTERMS

IAO_EXAMPLE = URIRef("http://purl.obolibrary.org/obo/IAO_0000112")
XSD = "http://www.w3.org/2001/XMLSchema#"
ROLE_NAMES = {"grouping": "grouping", "preprocessing": "preprocessing",
              "mapping": "mapping", "lookupOnly": "lookupOnly"}


@dataclass
class Field:
    name: str                 # local name, e.g. hasClaimDirection
    iri: str
    curie: str
    alt: str                  # skos:altLabel, the ASCII-safe key
    label: str
    description: str
    examples: list
    sections: list
    role: str                 # extracted | grouping | preprocessing | mapping | lookupOnly
    domain: str               # class label, e.g. Claim
    range_kind: str           # none | enum | datatype | class
    range_name: str
    parent: str               # local name of parent property, or ''
    path: list = field(default_factory=list)   # altLabels from the root group to this field
    prompt: dict = None
    prompt_property: str = ""
    citations: list = field(default_factory=list)
    comment: str = ""


class Cdbo:
    def __init__(self, path):
        self.g = Graph()
        self.g.parse(path, format="turtle")
        g = self.g
        ns = dict(g.namespaces())
        self.ns = str(ns["cdbo"])
        self.NS = lambda local: URIRef(self.ns + local)
        self.ontology_iri = next(g.subjects(RDF.type, OWL.Ontology))
        self.version = str(g.value(self.ontology_iri, OWL.versionInfo) or "")
        self.enums = self._enums()
        self.classes = {c: str(g.value(c, RDFS.label)) for c in g.subjects(RDF.type, OWL.Class)}
        self.fields = self._fields()
        self.by_name = {f.name: f for f in self.fields}
        for f in self.fields:
            f.path = self._path(f)

    # enumerated datatypes: owl:equivalentClass [ owl:oneOf (...) ]
    def _enums(self):
        out = {}
        for dt in self.g.subjects(RDF.type, RDFS.Datatype):
            if not str(dt).startswith(self.ns):
                continue
            for eq in self.g.objects(dt, OWL.equivalentClass):
                lst = self.g.value(eq, OWL.oneOf)
                if lst is not None:
                    out[str(dt)[len(self.ns):]] = [str(x) for x in Collection(self.g, lst)]
        return out

    def _fields(self):
        g, NS = self.g, self.NS
        prompt_props = {NS("hasStudyMetadataExtractionPrompt"): "hasStudyMetadataExtractionPrompt",
                        NS("hasClaimExtractionPrompt"): "hasClaimExtractionPrompt"}
        out = []
        for s in g.subjects(RDF.type, OWL.AnnotationProperty):
            if g.value(s, NS("hasCompactURI")) is None or not str(s).startswith(self.ns):
                continue
            name = str(s)[len(self.ns):]
            role_iri = g.value(s, DCTERMS.type)
            role = str(role_iri)[len(self.ns):] if role_iri is not None else "extracted"
            dom = g.value(s, RDFS.domain)
            rng = g.value(s, RDFS.range)
            if rng is None:
                kind, rname = "none", ""
            elif str(rng).startswith(self.ns) and str(rng)[len(self.ns):] in self.enums:
                kind, rname = "enum", str(rng)[len(self.ns):]
            elif rng in self.classes:
                kind, rname = "class", self.classes[rng]
            else:
                kind, rname = "datatype", str(rng).replace(XSD, "xsd:").replace(str(RDF), "rdf:")
            parent = g.value(s, RDFS.subPropertyOf)
            prompt, pprop = None, ""
            for pp, pn in prompt_props.items():
                v = g.value(s, pp)
                if v is not None:
                    prompt, pprop = json.loads(str(v)), pn
            out.append(Field(
                name=name, iri=str(s), curie="cdbo:" + name,
                alt=str(g.value(s, SKOS.altLabel) or ""),
                label=str(g.value(s, RDFS.label) or ""),
                description=str(g.value(s, DCTERMS.description) or ""),
                examples=[str(x) for x in g.objects(s, IAO_EXAMPLE)],
                sections=sorted(str(x) for x in g.objects(s, NS("hasTypicalArticleSection"))),
                role=role, domain=str(g.value(dom, RDFS.label)) if dom is not None else "",
                range_kind=kind, range_name=rname,
                parent=str(parent)[len(self.ns):] if parent is not None and str(parent).startswith(self.ns) else "",
                prompt=prompt, prompt_property=pprop,
                citations=[str(x) for x in g.objects(s, DCTERMS.bibliographicCitation)],
                comment=str(g.value(s, RDFS.comment) or "")))
        return sorted(out, key=lambda f: f.name)

    def _path(self, f):
        chain, cur, seen = [], f, set()
        while cur is not None and cur.name not in seen:
            seen.add(cur.name)
            chain.append(cur.alt)
            cur = self.by_name.get(cur.parent)
        return list(reversed(chain))

    def children(self, name):
        return [f for f in self.fields if f.parent == name]

    def roots(self):
        return [f for f in self.fields if not f.parent]

    def general_prompt(self, group_name, prompt_prop):
        v = self.g.value(self.NS(group_name), self.NS(prompt_prop))
        return json.loads(str(v)) if v is not None else None

    def extracted(self, domain):
        return [f for f in self.fields if f.role == "extracted" and f.domain == domain]
