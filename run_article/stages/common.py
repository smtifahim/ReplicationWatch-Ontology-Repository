"""Shared paths, constants and small helpers for the single-article ClaimsDB pipeline run."""
import csv, datetime, hashlib, json, os, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
CDBO_DIR = ROOT / "cdbo"
ONT_DIR = pathlib.Path(os.environ.get("ONT_DIR", ROOT / "ont"))
IN = ROOT / "inputs"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

CDBO_NS = "https://w3id.org/replicationwatch/cdbo/"
CSDO_NS = "https://w3id.org/replicationwatch/csdo/"
ID_NS = "https://w3id.org/replicationwatch/claimsdb/id/"   # placeholder namespace for instances, like the ontology IRIs
CDBO_VERSION = "0.4.1-draft"
CSDO_VERSION = "0.1.0-draft"
PUB_ID, STUDY_ID = "SE-P1", "SE-S1"
CLAIM_ID = lambda i: f"SE-C{i:02d}"

PREFIXES = {
    "cdbo": CDBO_NS, "csdo": CSDO_NS, "grp": CSDO_NS + "group/", "rwid": ID_NS, "pub": ID_NS + "pub/", "study": ID_NS + "study/", "claim": ID_NS + "claim/",
    "obo": "http://purl.obolibrary.org/obo/", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#", "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#", "dcterms": "http://purl.org/dc/terms/",
    "nidm": "http://purl.org/nidash/nidm#",
}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_json(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def obo_iri(curie):
    p, l = curie.split(":")
    return f"http://purl.obolibrary.org/obo/{p}_{l}"


def field_table():
    """Field_Key -> dict(compact, value_type, applies_to, role) from the generated data dictionary."""
    rows = csv.DictReader(open(CDBO_DIR / "out" / "data_dictionary.csv", encoding="utf-8-sig"))
    return {r["Field_Key"]: dict(compact=r["Compact_URI"], vtype=r["Value_Type"], applies=r["Applies_To"], role=r["Role"]) for r in rows}
