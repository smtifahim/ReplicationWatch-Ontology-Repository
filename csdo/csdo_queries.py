"""Read the SPARQL queries out of the CSDO ontology, in the order a loader needs them.

    from csdo_queries import load_queries, fill
    q = load_queries("csdo-core-v0.1.ttl")
    q["load_construct"]   # list of query strings, in execution order
    q["load_report"]      # list of SELECT strings
    q["portal_construct"], q["portal_select"]
    fill(text, FOCUS="<https://.../group/abc>", CRITERIA_SET="csdo:DefaultAnchor")
"""
import re
from rdflib import Graph, URIRef

BASE = "https://w3id.org/replicationwatch/csdo/"


def load_queries(ttl):
    g = Graph().parse(ttl, format="turtle")
    P = lambda n: URIRef(BASE + n)
    construct = sorted(((int(g.value(s, P("hasExecutionOrder"))), str(q)) for s, q in g.subject_objects(P("hasLoadConstructQuery"))))
    return {"load_construct": [q for _, q in construct],
            "load_report": sorted(str(q) for q in g.objects(None, P("hasLoadReportQuery"))),
            "portal_construct": sorted(str(q) for q in g.objects(None, P("hasPortalConstructQuery"))),
            "portal_select": sorted(str(q) for q in g.objects(None, P("hasPortalSelectQuery")))}


def fill(text, **params):
    """Replace {{NAME}} parameters. Values must already be IRIs in angle brackets or prefixed names."""
    for k, v in params.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise ValueError(f"unfilled parameters: {sorted(set(left))}")
    return text
