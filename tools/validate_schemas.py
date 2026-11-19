#!/usr/bin/env python3
"""Check the generated schemas: metaschema validity, a sample instance built
from the ontology examples, and negative tests. Usage: python validate_schemas.py ttl out/"""
import json, sys
from jsonschema import Draft202012Validator
from cdbo_common import Cdbo

def sample(o, domain):
    inst = {}
    for f in o.extracted(domain):
        ex = f.examples[0] if f.examples else ""
        inst[f.alt] = ex
    return inst

def main(ttl, out):
    o = Cdbo(ttl); ok = True
    for name, domain in (("study", "Study"), ("claims", "Claim")):
        sch = json.load(open(f"{out}/{name}.schema.json"))
        Draft202012Validator.check_schema(sch)
        v = Draft202012Validator(sch)
        inst = sample(o, domain)
        doc = inst if name == "study" else {"claims": [inst]}
        errs = list(v.iter_errors(doc))
        print(f"{name}: metaschema OK; sample instance errors: {len(errs)}")
        for e in errs: print("   ", e.message[:150]); ok = False
        # negative tests
        bad = json.loads(json.dumps(doc))
        tgt = bad if name == "study" else bad["claims"][0]
        tgt["Unexpected_Field"] = "x"
        neg1 = len(list(v.iter_errors(bad))) > 0
        bad2 = json.loads(json.dumps(doc)); t2 = bad2 if name == "study" else bad2["claims"][0]
        t2.pop(next(iter(t2)))
        neg2 = len(list(v.iter_errors(bad2))) > 0
        neg3 = True
        if name == "claims":
            bad3 = json.loads(json.dumps(doc)); bad3["claims"][0]["Claim_Direction"] = "Went up"
            neg3 = len(list(v.iter_errors(bad3))) > 0
            empty = len(list(v.iter_errors({"claims": []}))) == 0
            print(f"   empty claims array accepted: {empty}"); ok &= empty
        print(f"   rejects extra key: {neg1}; rejects missing key: {neg2}; rejects bad enum: {neg3}")
        ok &= neg1 and neg2 and neg3
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
