#!/usr/bin/env python3
"""Generate the Claim Similarity Dimension Ontology (CSDO) from this file and the query sources in queries/.

Usage: python gen_csdo.py ../cdbo-core-v0.3.ttl ../csdo-core-v0.1.ttl
The SPARQL queries are stored as annotation property values, so the ontology is the single place where the loader
and the portal get them from.
"""
import os
import sys
from rdflib import Graph, Namespace, URIRef, Literal, BNode, RDF, RDFS, OWL, XSD
from rdflib.collection import Collection
from rdflib.namespace import SKOS, DCTERMS, DC

CDBO_TTL, OUT = sys.argv[1], sys.argv[2]
QDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queries")
VERSION = "0.1.0-draft"
BASE = "https://w3id.org/replicationwatch/csdo/"          # PLACEHOLDER namespace
CBASE = "https://w3id.org/replicationwatch/cdbo/"
CSDO, CDBO = Namespace(BASE), Namespace(CBASE)
OBO = Namespace("http://purl.obolibrary.org/obo/")
cg = Graph().parse(CDBO_TTL, format="turtle")
CDBO_VERSION = str(cg.value(URIRef(CBASE + "claimsdb-core.owl"), OWL.versionInfo))

g = Graph()
for p, n in [("csdo", CSDO), ("cdbo", CDBO), ("obo", OBO), ("owl", OWL), ("rdf", RDF), ("rdfs", RDFS), ("xsd", XSD),
             ("skos", SKOS), ("dcterms", DCTERMS), ("dc", DC)]:
    g.bind(p, n)
ONT = URIRef(BASE + "csdo-core.owl")
g.add((ONT, RDF.type, OWL.Ontology))
g.add((ONT, OWL.imports, URIRef(CBASE + "claimsdb-core.owl")))
g.add((ONT, DC.title, Literal("Claim Similarity Dimension Ontology (CSDO) Core")))
g.add((ONT, DC.creator, Literal("Fahim Imam - https://orcid.org/0000-0003-4752-543X")))
g.add((ONT, DC.date, Literal("November 5, 2026")))
g.add((ONT, DC.description, Literal(
    "This ontology defines how claims in ClaimsDB are compared. Claim records that report the same finding are grouped, and two groups "
    "that share the required anchor (the same grounded condition and brain region) are linked by an RDF-star edge whose properties "
    "record how the groups relate on laterality, measure and direction. The links are candidates for expert review, not verdicts. "
    "The SPARQL queries that build and read the groups and edges are stored in the ontology as annotation properties. "
    "The reference deployment uses Stardog. The model uses standard RDF and RDF-star edges, so other standard graph databases that "
    "support RDF-star can be used with at most changes to the query dialect.", lang="en")))
g.add((ONT, RDFS.comment, Literal(f"""DRAFT v{VERSION}. Imports the ClaimsDB Ontology (CDBO), version {CDBO_VERSION}. Contents:
- Two classes: Claim Group and Criteria Set.
- Group slot properties and the edge properties (relations) with restricted datatypes.
- Two criteria sets: the default anchor (condition and region) and the anchor plus measure.
- SPARQL queries as annotation properties: load queries (run in order after each finished batch, results merged into the knowledge base), load reports, and portal queries.
- The namespace IRI is a placeholder and no license is set yet.""", lang="en")))
g.add((ONT, OWL.versionInfo, Literal(VERSION, lang="en")))

REF = {
 "MICRO": "Clark T, Ciccarese PN, Goble CA. Micropublications: a semantic model for claims, evidence, arguments and annotations in biomedical communications. Journal of Biomedical Semantics 2014;5:28. doi:10.1186/2041-1480-5-28",
 "SHACLAF": "RDF Data Shapes Working Group. SHACL Advanced Features. W3C Working Group Note, 8 June 2017. https://www.w3.org/TR/2017/NOTE-shacl-af-20170608",
 "RDFSTAR": "RDF-star Community Group. RDF-star and SPARQL-star. Community Group report, version of 13 April 2021. https://w3c.github.io/rdf-star/cg-spec/2021-04-13.html"}

def cite(s, keys, comment):
    for k in keys:
        g.add((s, DCTERMS.bibliographicCitation, Literal(REF[k])))
    g.add((s, RDFS.comment, Literal(comment, lang="en")))

def common(s, label, alt, desc):
    g.add((s, RDFS.label, Literal(label, lang="en")))
    g.add((s, SKOS.altLabel, Literal(alt)))
    g.add((s, DCTERMS.description, Literal(desc, lang="en")))
    local = str(s)[len(BASE):]
    g.add((s, CDBO.hasCompactURI, Literal("csdo:" + local)))

def cls(local, label, alt, desc):
    s = CSDO[local]; g.add((s, RDF.type, OWL.Class)); common(s, label, alt, desc); return s

# datatypes
def enum(name, values):
    dt = CSDO[name]; g.add((dt, RDF.type, RDFS.Datatype))
    b, l = BNode(), BNode(); g.add((b, RDF.type, RDFS.Datatype))
    Collection(g, l, [Literal(v) for v in values]); g.add((b, OWL.oneOf, l)); g.add((dt, OWL.equivalentClass, b)); return dt
SDU = enum("sameDifferentUnknownType", ["Same", "Different", "Unknown"])
DIRREL = enum("directionRelationType", ["Concordant", "Opposite", "NullVsEffect", "NotComparable"])

GROUP = cls("CSDO_0000001", "Claim Group", "Claim_Group",
    "A derived node that stands for all Claim records with the same complete claim key (condition, region, laterality, measure and direction). "
    "A Claim record with an incomplete key forms a group of its own and is never merged. Groups are rebuilt from the Claim records, so they can be regenerated at any time. "
    "The number of member records, split by age group and evidence level, is the support for the finding.")
CSET = cls("CSDO_0000002", "Criteria Set", "Criteria_Set",
    "A choice of which slots two claim groups must share for a comparison to be proposed. Each required slot is an exact match of the grounded value.")

def prop(local, kind, label, alt, desc, domain=None, rng=None):
    s = CSDO[local]; g.add((s, RDF.type, kind)); common(s, label, alt, desc)
    if domain is not None: g.add((s, RDFS.domain, domain))
    if rng is not None: g.add((s, RDFS.range, rng))
    return s

OP, DP, AP = OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty
CLAIM = CDBO["CDBO_0000003"]
inGroup = prop("inClaimGroup", OP, "in claim group", "In_Claim_Group", "Links a Claim record to the Claim Group that contains it.", CLAIM, GROUP)
comparable = prop("comparableTo", OP, "comparable to", "Comparable_To",
    "A candidate comparison between two Claim Groups that share the required anchor. It is stored once per pair, in IRI order, and is symmetric in meaning. "
    "It is used as an RDF-star edge: the quoted triple is the subject of the edge properties (criteria set, the three relations and the versions used). "
    "The link says that experts should compare the two groups. It does not say that one confirms or refutes the other.", GROUP, GROUP)
g.add((comparable, RDF.type, OWL.SymmetricProperty))
cite(comparable, ["RDFSTAR"], "Edge properties are expressed with RDF-star quoted triples, which are the subject of the edge properties. Stardog is the reference deployment; the same model can be used in other graph databases that support RDF-star.")
prop("hasCondition", OP, "has condition", "Group_Condition", "The grounded condition or variable of interest of the group, copied from its member records (a community ontology IRI, or a provisional local IRI until curated).", GROUP)
prop("hasRegion", OP, "has region", "Group_Region", "The grounded brain region of the group, copied from its member records.", GROUP)
prop("hasLaterality", DP, "has laterality", "Group_Laterality", "The laterality of the group, copied from its member records.", GROUP, CDBO["lateralityType"])
prop("hasMeasure", DP, "has measure", "Group_Measure", "The grounded measure of the group as a string, copied from its member records.", GROUP, XSD.string)
prop("hasDirection", DP, "has direction", "Group_Direction", "The direction of the finding of the group, copied from its member records.", GROUP, CDBO["directionType"])
prop("isComplete", DP, "is complete", "Group_Is_Complete", "True when the group was formed from a complete claim key. False for a group made of a single record with an incomplete key.", GROUP, XSD.boolean)
# edge properties
prop("criteriaSet", OP, "criteria set", "Criteria_Set_Used", "Edge property. The criteria set under which the two groups were compared.", None, CSET)
prop("lateralityRelation", DP, "laterality relation", "Laterality_Relation",
     "Edge property. Same or Different when both groups state a laterality, otherwise Unknown (Not Specified counts as Unknown).", None, SDU)
prop("measureRelation", DP, "measure relation", "Measure_Relation", "Edge property. Same or Different when both groups have a grounded measure, otherwise Unknown.", None, SDU)
dr = prop("directionRelation", DP, "direction relation", "Direction_Relation",
     "Edge property. Concordant when both groups report the same direction. Opposite when one reports an increase (or positive association) and the other a decrease (or negative association). "
     "NullVsEffect when one reports no difference (or no association) and the other reports an effect. NotComparable when one group reports a group difference and the other an association.", None, DIRREL)
cite(dr, ["MICRO"], "Concordant corresponds to the supports relation of micropublications. Opposite and NullVsEffect correspond to challenges. The system proposes candidate links and does not issue replicated or refuted verdicts.")
prop("computedWithVersions", DP, "computed with versions", "Computed_With_Versions", "Edge property. The CSDO and CDBO versions used to compute the edge, so edges can be rebuilt when the ontologies change.", None, XSD.string)
# criteria set properties
for slot in ["Condition", "Region", "Laterality", "Measure", "Direction"]:
    prop("requires" + slot, DP, f"requires {slot.lower()}", f"Requires_{slot}", f"True when two groups must have the same grounded {slot.lower()} for the criteria set to propose a comparison.", CSET, XSD.boolean)
# criteria set individuals
def individual(local, label, alt, desc, req):
    s = CSDO[local]; g.add((s, RDF.type, OWL.NamedIndividual)); g.add((s, RDF.type, CSET)); common(s, label, alt, desc)
    for slot in ["Condition", "Region", "Laterality", "Measure", "Direction"]:
        g.add((s, CSDO["requires" + slot], Literal(slot in req)))
individual("DefaultAnchor", "Default anchor", "Default_Anchor", "The default criteria set: the same grounded condition and the same grounded region. This is the only set whose edges are stored by the load queries.", {"Condition", "Region"})
individual("AnchorPlusMeasure", "Anchor plus measure", "Anchor_Plus_Measure", "The anchor plus the same grounded measure. Evaluated at request time by the portal query.", {"Condition", "Region", "Measure"})

# query annotation properties
sparql = prop("hasSparqlQuery", AP, "has SPARQL query", "Has_Sparql_Query",
    "A SPARQL query, as a self-contained string that includes its PREFIX declarations, attached to the term it produces or reads. "
    "Queries use standard SPARQL 1.1 and RDF-star quoted triples as the subject of edge properties.")
cite(sparql, ["SHACLAF"], "Storing a SPARQL CONSTRUCT query as an xsd:string property value follows the SPARQL rules of SHACL Advanced Features (sh:construct), a W3C Working Group Note. CSDO uses its own properties and does not rely on SHACL rule execution.")
QP = {}
for local, label, alt, desc in [
    ("hasLoadConstructQuery", "has load CONSTRUCT query", "Has_Load_Construct_Query", "A CONSTRUCT query that the loader runs after each finished batch, in the order given by csdo:hasExecutionOrder. The returned graph is merged into the knowledge base."),
    ("hasLoadReportQuery", "has load report query", "Has_Load_Report_Query", "A SELECT query that the loader runs after the load queries to report how many records are invisible to the default anchor and how large the anchors are."),
    ("hasPortalConstructQuery", "has portal CONSTRUCT query", "Has_Portal_Construct_Query", "A CONSTRUCT query that the portal runs for one selected claim group. Parameters in double braces are replaced by IRIs."),
    ("hasPortalSelectQuery", "has portal SELECT query", "Has_Portal_Select_Query", "A SELECT query that the portal runs. Parameters in double braces are replaced by IRIs.")]:
    QP[local] = prop(local, AP, label, alt, desc); g.add((QP[local], RDFS.subPropertyOf, sparql)); g.add((QP[local], RDFS.range, XSD.string))
g.add((sparql, RDFS.range, XSD.string))
order = prop("hasExecutionOrder", AP, "has execution order", "Has_Execution_Order", "The position in which the load CONSTRUCT queries of different terms are run. Each value is unique.")
g.add((order, RDFS.range, XSD.integer))

PREFIXES = "\n".join(f"PREFIX {p}: <{u}>" for p, u in [("cdbo", CBASE), ("csdo", BASE), ("rdf", str(RDF)), ("rdfs", str(RDFS)), ("xsd", str(XSD))]) + "\n"
VERSIONS = f"CSDO {VERSION}; CDBO {CDBO_VERSION}"
def q(name):
    return PREFIXES + open(os.path.join(QDIR, name + ".rq"), encoding="utf-8").read().replace("__VERSIONS__", VERSIONS)

g.add((GROUP, QP["hasLoadConstructQuery"], Literal(q("load_groups")))); g.add((GROUP, order, Literal(1)))
g.add((comparable, QP["hasLoadConstructQuery"], Literal(q("load_edges")))); g.add((comparable, order, Literal(2)))
g.add((GROUP, QP["hasLoadReportQuery"], Literal(q("load_report_counts"))))
g.add((GROUP, QP["hasLoadReportQuery"], Literal(q("load_report_buckets"))))
g.add((CSET, QP["hasPortalConstructQuery"], Literal(q("portal_neighbours"))))
g.add((GROUP, QP["hasPortalSelectQuery"], Literal(q("portal_broader_region"))))
g.add((GROUP, QP["hasPortalSelectQuery"], Literal(q("portal_group_members"))))
g.serialize(OUT, format="turtle")
print(f"CSDO {VERSION}: {len(g)} triples -> {OUT}")
