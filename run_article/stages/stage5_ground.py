"""Stage 5: deterministic grounding. The LLM never grounds.
Condition  MONDO first (exact label or EXACT synonym), HP only when MONDO fails.
Region     UBERON, exact label or EXACT synonym.
Measure    PATO quality by whole-word patterns from cdbo/config/grounding_seed.json; a tissue named in the measure (gray matter) is looked up in UBERON and appended.
Laterality direct lookup (BSPO, PATO) from the seed file.
Study      imaging modality to the NIDM slice by rule. Software, dataset and article lookups (RRID, InterLex, BioPortal, SciScore, Crossref) need the network and
           are NOT run here; they are written to the curation queue as 'not looked up' rather than invented.
A term that does not ground goes to the *_Unmappable field and the curation queue, with advisory near-matches. Near-matches are never applied.
BioPortal Annotator and InterLex are the planned fallbacks after OAK; they are not reachable from this environment, so the fallback step is recorded as skipped."""
import re
from rdflib import Graph, RDFS
from common import *
from obo import Obo

STUDY_MODALITY_RULES = [  # (regex on Imaging_Modality text, NIDM CURIE)
    (r"\bMRI\b|magnetic resonance", "nidm:MagneticResonanceImaging"),
    (r"structural", "nidm:Structural"),
    (r"\bT1\b|T1-weighted", "nidm:T1Weighted"),
]


class Grounder:
    def __init__(self):
        self.U = Obo(ONT_DIR / "uberon-edit.obo", "UBERON:")
        self.M = Obo(ONT_DIR / "mondo-edit.obo", "MONDO:")
        self.H = Obo(ONT_DIR / "hp.obo", "HP:")
        self.seed = json.loads((CDBO_DIR / "config" / "grounding_seed.json").read_text())
        self.slice_labels, self.slice_files = {}, {}
        for f, pref in (("pato-imaging-slice.ttl", "PATO"), ("bspo-laterality-slice.ttl", "BSPO"), ("nidm-imaging-slice.ttl", "nidm")):
            p = CDBO_DIR / "imports" / f
            g = Graph().parse(p, format="turtle")
            self.slice_files[pref] = dict(file=f, sha256=sha256_file(p)[:12])
            for s, o in g.subject_objects(RDFS.label):
                s = str(s)
                if pref == "nidm": c = "nidm:" + s.split("#")[-1]
                else: c = s.split("/")[-1].replace("_", ":")
                self.slice_labels[c] = str(o)
        self.slice_labels.setdefault("PATO:0000618", "bilateral")
        self.versions = {"UBERON": self.U.version, "MONDO": self.M.version, "HP": self.H.version,
                         "PATO": "slice " + self.slice_files["PATO"]["sha256"], "BSPO": "slice " + self.slice_files["BSPO"]["sha256"],
                         "NIDM": "slice " + self.slice_files["nidm"]["sha256"], "grounding_seed": sha256_file(CDBO_DIR / "config" / "grounding_seed.json")[:12]}

    def label(self, curie):
        for o in (self.U, self.M, self.H):
            if curie in o.name: return o.name[curie]
        return self.slice_labels.get(curie)

    def _report(self, onto, term, ontology):
        i, status, info = onto.exact(term)
        return i, status, info

    def condition(self, term):
        steps = []
        for onto, name in ((self.M, "MONDO"), (self.H, "HP")):
            i, status, info = onto.exact(term)
            steps.append(dict(ontology=name, status=status))
            if i:
                return dict(curie=i, label=onto.name[i], ontology=name, match=info[1], via=info[2], status="matched", steps=steps)
        sug = self.M.suggest(term, 3) + self.H.suggest(term, 3)
        return dict(curie=None, status=("ambiguous" if any(s["status"] == "ambiguous" for s in steps) else "unmatched"), steps=steps, suggestions=sug[:5])

    def region(self, term):
        i, status, info = self.U.exact(term)
        if i: return dict(curie=i, label=self.U.name[i], ontology="UBERON", match=info[1], via=info[2], status="matched")
        rel = [dict(curie=h[0], label=self.U.name[h[0]], match=h[1], via=h[2]) for h in (info if status == "related_only" else [])]
        return dict(curie=None, status=status if status != "none" else "unmatched", related_only=rel, suggestions=self.U.suggest(term, 5))

    def measure(self, text):
        tl = text.lower()
        for q in self.seed["measure_quality"]:
            if any(re.search(r"\b" + re.escape(p) + r"\b", tl) for p in q["patterns"]):
                out = [dict(curie=q["curie"], label=self.label(q["curie"]), ontology="PATO")]
                if "gray matter" in tl:
                    t = self.region("gray matter")
                    if t["curie"]: out.append(dict(curie=t["curie"], label=t["label"], ontology="UBERON"))
                return dict(curies=[o["curie"] for o in out], terms=out, status="matched")
        return dict(curies=None, status="unmatched", suggestions=[])

    def laterality(self, value):
        c = self.seed["laterality"].get(value)
        return dict(curie=c, label=self.label(c) if c else None, status="matched" if c else "not_applicable")

    def modality(self, text):
        cur = [c for rx, c in STUDY_MODALITY_RULES if re.search(rx, text, re.I)]
        return dict(curies=cur or None, terms=[dict(curie=c, label=self.label(c)) for c in cur], status="matched" if cur else "unmatched")


def run(claims, study):
    g = Grounder()
    recs = []
    for i, c in enumerate(claims, 1):
        r = dict(id=CLAIM_ID(i), condition=g.condition(c["Claim_Condition"]), region=g.region(c["Claim_Region"]),
                 measure=g.measure(c["Claim_Measure"]), laterality=g.laterality(c["Claim_Laterality"]))
        recs.append(r)
    sg = dict(modality=g.modality(study["Imaging_Modality"]))
    out = dict(versions=g.versions, claims=recs, study=sg,
               ontology_files={k: dict(file=str(p.name), sha256=o.sha256, version=o.version, terms=len(o.name))
                               for k, p, o in (("UBERON", ONT_DIR / "uberon-edit.obo", g.U), ("MONDO", ONT_DIR / "mondo-edit.obo", g.M), ("HP", ONT_DIR / "hp.obo", g.H))},
               fallbacks=dict(bioportal_annotator="skipped: not reachable from this environment", interlex="skipped: not reachable from this environment"))
    save_json("stage5_grounding.json", out)
    return g, out


if __name__ == "__main__":
    import stage3_extract as s3
    c, s, _ = s3.run(); g, o = run(c, s)
    print(json.dumps(o["versions"], indent=1)); print(o["ontology_files"])
    for r in o["claims"]:
        print(r["id"], r["condition"].get("curie"), r["condition"].get("ontology"), "|", r["region"].get("curie"), r["region"]["status"], "|", r["measure"]["curies"], "|", r["laterality"]["curie"])
    for r in o["claims"]:
        for k in ("condition", "region"):
            if r[k]["status"] != "matched": print(r["id"], k, r[k]["status"], r[k].get("suggestions"), r[k].get("related_only"))
    print(o["study"])
