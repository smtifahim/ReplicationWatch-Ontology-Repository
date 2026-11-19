"""Stage 3: LLM extraction (claims call and study call).
In production both calls go to the API with the prompts and JSON schemas generated from the ontology (cdbo/out/*.prompt.json, *.schema.json).
In THIS run no API key was available, so the two calls were performed by Claude in the working session on the same article text with the same
fields and rules; their JSON outputs are stored in inputs/ and loaded here unchanged. The provenance fields say so."""
import hashlib, json
from common import *


def run():
    claims = json.loads((IN / "claims_out.json").read_text(encoding="utf-8"))["claims"]
    study = json.loads((IN / "study_out.json").read_text(encoding="utf-8"))
    ph = hashlib.sha256(b"".join((CDBO_DIR / "out" / n).read_bytes() for n in ("claims.prompt.json", "study.prompt.json"))).hexdigest()[:12]
    prov = {
        "Extraction_Model_ID": "claude-sonnet-5-5 (configured model; calls run in-session, not through the API; the serving model may differ)",
        "Extraction_Prompt_Version": f"CDBO {CDBO_VERSION} prompts (claims.prompt.json + study.prompt.json, sha256 {ph})",
        "Ontology_Version": f"CDBO {CDBO_VERSION}; CSDO {CSDO_VERSION}",
        "Extraction_Date": now_utc(),
    }
    save_json("stage3_extraction.json", dict(provenance=prov, n_claims=len(claims), study=study, claims=claims))
    return claims, study, prov


if __name__ == "__main__":
    c, s, p = run(); print(len(c), len(s), p)
