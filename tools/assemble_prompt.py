#!/usr/bin/env python3
"""Assemble the prompt for one LLM call from the CDBO ontology.

Usage: python assemble_prompt.py ../ontologies/cdbo-core-v0.4.1.ttl study|claims [out.json]

The system prompt is the root general prompt plus the call's general prompt.
The fragments are the per-field prompts. Both come from the ontology, so
changing a definition, example or rule in the ontology changes the prompt.
The static prefix (system prompt plus fragments) is identical for every
article, so it is the part to cache.
"""
import json
import sys
from cdbo_common import Cdbo


def assemble(o, call):
    domain = "Study" if call == "study" else "Claim"
    group, prop = (("hasStudyMetadata", "hasGeneralStudyMetadataExtractionPrompt") if call == "study"
                   else ("hasClaimRecordMetadata", "hasGeneralClaimExtractionPrompt"))
    root = o.general_prompt("hasClaimsDBMetadata", "hasGeneralClaimsDBExtractionPrompt")
    grp = o.general_prompt(group, prop)
    frags = [f.prompt for f in sorted(o.extracted(domain), key=lambda x: (x.path, x.name))]
    return {"system": {"pipeline": root, "this_call": grp}, "field_fragments": frags,
            "output_schema_file": f"{call}.schema.json"}


if __name__ == "__main__":
    o = Cdbo(sys.argv[1])
    call = sys.argv[2]
    p = assemble(o, call)
    text = json.dumps(p, ensure_ascii=False)
    print(f"{call}: {len(p['field_fragments'])} field fragments, {len(text)} characters "
          f"(about {len(text)//4} tokens, rough estimate at 4 characters per token)")
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            json.dump(p, fh, indent=2, ensure_ascii=False)
