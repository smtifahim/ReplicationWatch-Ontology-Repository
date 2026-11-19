"""Stage 4: validation gates. Nothing here changes an extracted value. A gate failure becomes a flag in the curation queue.
G1  JSON Schema: claims and study outputs against the schemas generated from the ontology.
G2  Evidence quote is verbatim in the parsed article text (tiered: exact, whitespace and hyphenation normalised, squeezed).
G3  Numbers in Claim_P_Value occur in the article text (catches a hallucinated value).
G4  Claim_Source_Reference (Table or Figure label) is mentioned in the article text; an empty reference is allowed but warned.
G5  Duplicate claim statements and quotes reused by more than one claim are reported (informational)."""
import re, unicodedata
from jsonschema import Draft202012Validator
from common import *

HEADER_NOISE = re.compile(r"\d{5,}, 20\d\d, \d, Downloaded from https?://\S+ by .*?rules of use; OA articles are governed by the applicable Creative Commons License", re.S)
RUNNING = re.compile(r"Developmental Science,? 20\d\d \d+ of \d+|© 20\d\d John Wiley & Sons Ltd\.?|Developmental Science, 20\d\d; \d+:e\d+ https://doi\.org/\S+ \d+ of \d+")


def norm(s, level):
    s = unicodedata.normalize("NFKC", s).replace("­", "")
    s = HEADER_NOISE.sub(" ", s)
    s = RUNNING.sub(" ", s)
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"-\s*\n\s*", "", s) if level >= 1 else s
    s = re.sub(r"\s+", " ", s).strip()
    if level >= 2:
        s = re.sub(r"[\s\-‐-―]", "", s)
    return s


def find_quote(quote, page_text):
    """Return (tier, page) for the first tier at which the quote occurs in the article, else (None, None)."""
    full = "\n".join(page_text)
    for tier, level in (("exact", 0), ("normalised", 1), ("squeezed", 2)):
        q = norm(quote, level)
        if level == 0:
            q = re.sub(r"\s+", " ", quote).strip()
            if q in re.sub(r"\s+", " ", full): return tier, _page(q, page_text, 0)
            continue
        if q and q in norm(full, level): return tier, _page(quote, page_text, level)
    return None, None


def _page(quote, page_text, level):
    q = norm(quote, level) if level else re.sub(r"\s+", " ", quote).strip()
    for i, p in enumerate(page_text, 1):
        pp = norm(p, level) if level else re.sub(r"\s+", " ", p)
        if q in pp: return i
    return None   # quote spans a page break


def run(claims, study, page_text):
    claims_schema = json.loads((CDBO_DIR / "out" / "claims.schema.json").read_text())
    study_schema = json.loads((CDBO_DIR / "out" / "study.schema.json").read_text())
    full_norm = norm("\n".join(page_text), 1)
    res = {"study_schema": [e.message for e in Draft202012Validator(study_schema).iter_errors(study)],
           "claims_schema": [f"claim {list(e.absolute_path)}: {e.message}" for e in Draft202012Validator(claims_schema).iter_errors({"claims": claims})],
           "claims": []}
    seen_q, seen_s = {}, {}
    for i, c in enumerate(claims, 1):
        cid = CLAIM_ID(i)
        tier, page = find_quote(c["Claim_Evidence_Quote"], page_text)
        nums = re.findall(r"\d+\.\d+|\d+", c.get("Claim_P_Value", "").replace("−", "-"))
        missing = [n for n in nums if n not in full_norm.replace("−", "-")]
        ref = c.get("Claim_Source_Reference", "")
        ref_ok = (ref == "" ) or (ref.lower() in full_norm.lower())
        seen_q.setdefault(c["Claim_Evidence_Quote"], []).append(cid)
        seen_s.setdefault(c["Claim_Statement"], []).append(cid)
        res["claims"].append(dict(
            id=cid, quote_tier=tier, quote_page=page, quote_ok=tier is not None,
            p_numbers=nums, p_numbers_missing=missing, p_ok=not missing,
            reference=ref, reference_empty=(ref == ""), reference_ok=ref_ok, section=c["Claim_Source_Section"]))
    res["shared_quotes"] = {q[:80]: ids for q, ids in seen_q.items() if len(ids) > 1}
    res["duplicate_statements"] = {q[:80]: ids for q, ids in seen_s.items() if len(ids) > 1}
    cl = res["claims"]
    res["summary"] = dict(
        claims=len(cl), schema_errors=len(res["study_schema"]) + len(res["claims_schema"]),
        quotes_exact=sum(c["quote_tier"] == "exact" for c in cl), quotes_normalised=sum(c["quote_tier"] == "normalised" for c in cl),
        quotes_squeezed=sum(c["quote_tier"] == "squeezed" for c in cl), quotes_failed=sum(not c["quote_ok"] for c in cl),
        p_value_numbers_not_in_text=sum(not c["p_ok"] for c in cl), empty_reference=sum(c["reference_empty"] for c in cl),
        reference_not_found=sum(not c["reference_ok"] for c in cl), shared_quotes=len(res["shared_quotes"]))
    save_json("stage4_validation.json", res)
    return res


if __name__ == "__main__":
    import stage1_registry as s1, stage3_extract as s3
    _, _, _, pt = s1.run(IN / "efd5369b-test.pdf"); c, s, _ = s3.run()
    r = run(c, s, pt); print(json.dumps(r["summary"], indent=1)); print(r["study_schema"], r["claims_schema"][:3]);
    for x in r["claims"]: print(x["id"], x["quote_tier"], x["quote_page"], x["p_ok"], x["reference_ok"], x["reference"])
    print(r["shared_quotes"].values())
