"""Stage 5b: claim merge. Builds the claim key from the grounded slots and derives the Claim Groups with the stored CSDO load query (pass 1).
Key = condition | region | laterality | measure (+ tissue) | direction.  A key with any ungrounded slot, or laterality 'Not Specified', is incomplete:
the record becomes its own group (hash of its claim IRI) and is never merged. Group IRIs are SHA1 hashes, so a re-run after every batch is idempotent."""
import pyoxigraph as ox
from common import *
import sys; sys.path.insert(0, str(CDBO_DIR / "csdo"))
from csdo_queries import load_queries

PFX = f"PREFIX cdbo: <{CDBO_NS}> PREFIX csdo: <{CSDO_NS}> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"


def claim_key(claim, gr):
    cond, reg = gr["condition"].get("curie"), gr["region"].get("curie")
    mea = gr["measure"].get("curies")
    lat = claim["Claim_Laterality"]
    key = "|".join([cond or "?", reg or "?", lat, "+".join(mea or ["?"]), claim["Claim_Direction"]])
    complete = bool(cond and reg and mea and lat != "Not Specified")
    return key, complete


def claim_iri(cid): return ID_NS + "claim/" + cid


def key_graph(rows):
    """rows: list of dict(id, key, complete, cond, reg, lat, mea, dir). Returns an Oxigraph store holding just the key predicates."""
    st = ox.Store()
    N = ox.NamedNode; L = ox.Literal; Q = lambda s, p, o: st.add(ox.Quad(s, N(CDBO_NS + p) if not p.startswith("http") else N(p), o, ox.DefaultGraph()))
    for r in rows:
        s = N(claim_iri(r["id"]))
        Q(s, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", N(CDBO_NS + "CDBO_0000003"))
        Q(s, "hasClaimKey", L(r["key"])); Q(s, "hasClaimKeyComplete", L("Yes" if r["complete"] else "No"))
        Q(s, "hasClaimLaterality", L(r["lat"])); Q(s, "hasClaimDirection", L(r["dir"]))
        if r["cond"]: Q(s, "hasMappedClaimCondition", N(obo_iri(r["cond"])))
        if r["reg"]: Q(s, "hasMappedClaimRegion", N(obo_iri(r["reg"])))
        if r["mea"]: Q(s, "hasMappedClaimMeasureCurie", L(json.dumps(r["mea"])))
    return st


def derive_groups(store):
    queries = load_queries(CDBO_DIR / "csdo-core-v0.1.ttl")
    store.load((CDBO_DIR / "csdo-core-v0.1.ttl").read_bytes(), format=ox.RdfFormat.TURTLE)
    q = queries["load_construct"][0]
    store.extend([ox.Quad(t.subject, t.predicate, t.object, ox.DefaultGraph()) for t in store.query(q)])
    members = {}
    for row in store.query(PFX + "SELECT ?c ?g WHERE { ?c csdo:inClaimGroup ?g }"):
        members.setdefault(row["g"].value, []).append(row["c"].value.rsplit("/", 1)[-1])
    return members, queries


def run(claims, ground):
    rows = []
    for c, gr in zip(claims, ground["claims"]):
        key, complete = claim_key(c, gr)
        rows.append(dict(id=gr["id"], key=key, complete=complete, cond=gr["condition"].get("curie"), reg=gr["region"].get("curie"),
                         lat=c["Claim_Laterality"], mea=gr["measure"].get("curies"), dir=c["Claim_Direction"]))
    st = key_graph(rows)
    members, _ = derive_groups(st)
    order = sorted(members, key=lambda g: min(members[g]))
    names = {g: f"G{i+1:02d}" for i, g in enumerate(order)}
    out = dict(claims=rows, groups=[dict(name=names[g], iri=g, claims=sorted(members[g])) for g in order],
               n_complete=sum(r["complete"] for r in rows), n_groups=len(order),
               merged_groups=[names[g] for g in order if len(members[g]) > 1])
    save_json("stage5b_merge.json", out)
    return out


if __name__ == "__main__":
    import stage3_extract as s3, stage5_ground as s5
    c, s, _ = s3.run(); g, o = s5.run(c, s); m = run(c, o)
    print(m["n_complete"], m["n_groups"], m["merged_groups"])
    for x in m["claims"]: print(x["id"], x["key"], x["complete"])
    for g in m["groups"]: print(g["name"], g["claims"])
