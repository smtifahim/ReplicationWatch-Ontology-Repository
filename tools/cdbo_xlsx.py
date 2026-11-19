"""Shared helpers for the CDBO Excel template: layout loading and column planning.

The ontology says WHAT the fields are. config/excel_layout.json says HOW they
are laid out (tabs, spans, column order, colours, widths). Keeping the layout
out of the ontology lets curators change it without touching the ontology.
"""
import json
from cdbo_common import Cdbo

HEADER_ROWS = 2          # row 1 = group span, row 2 = field key
KEY_ROW = 2
FIRST_DATA_ROW = 3


def load_layout(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def nearest_group(o, f):
    cur = o.by_name.get(f.parent)
    while cur is not None and cur.role != "grouping":
        cur = o.by_name.get(cur.parent)
    return cur


class Column:
    def __init__(self, key, field, span, identity=False):
        self.key, self.field, self.span, self.identity = key, field, span, identity


class TabPlan:
    def __init__(self, name, entity, group, columns, spans):
        self.name, self.entity, self.group = name, entity, group
        self.columns, self.spans = columns, spans   # spans: list of (group_alt, label, [Column])
        self.n_identity = sum(c.identity for c in columns)

    def col_index(self, key):
        for i, c in enumerate(self.columns, 1):
            if c.key == key:
                return i
        return None


def plan(o, layout):
    """Return (tab plans, warnings). Raises ValueError on an unusable layout."""
    by_alt = {f.alt: f for f in o.fields}
    warns, plans, covered = [], [], set()
    for t in layout["tabs"]:
        gname = t["group"]
        if gname not in by_alt or by_alt[gname].role != "grouping":
            raise ValueError(f"tab {t['name']}: '{gname}' is not a grouping property")
        ident_keys = layout["identity"][t["entity"]]
        for k in ident_keys:
            if k not in by_alt:
                raise ValueError(f"identity key '{k}' is not an ontology field")
        members = [f for f in o.fields if f.role != "grouping" and gname in f.path[:-1]]
        spans_map = {}
        for f in members:
            g = nearest_group(o, f)
            spans_map.setdefault(g.alt, []).append(f)
        want = layout.get("span_order", {}).get(gname, [])
        span_keys = [g for g in want if g in spans_map] + [g for g in spans_map if g not in want]
        for g in spans_map:
            if g not in want and len(spans_map) > 1:
                warns.append(f"{t['name']}: span '{g}' is not listed in span_order; appended")
        cols = [Column(k, by_alt[k], "Identity", True) for k in ident_keys]
        spans = [("Identity", "Identity (registry-assigned)", list(cols))]
        for g in span_keys:
            order = layout["field_order"].get(g, [])
            have = {f.alt: f for f in spans_map[g]}
            for k in order:
                if k not in have and k in by_alt:
                    warns.append(f"layout lists '{k}' under {g} but the ontology places it elsewhere")
            seq = [have[k] for k in order if k in have]
            for f in sorted(have.values(), key=lambda x: x.name):
                if f.alt not in order:
                    warns.append(f"{t['name']}: field '{f.alt}' missing from field_order[{g}]; appended")
                    seq.append(f)
            gcols = [Column(f.alt, f, g) for f in seq]
            cols += gcols
            spans.append((g, by_alt[g].label, gcols))
            covered.update(f.alt for f in seq)
        plans.append(TabPlan(t["name"], t["entity"], gname, cols, spans))
    ident_all = {k for ks in layout["identity"].values() for k in ks}
    for f in o.fields:
        if f.role != "grouping" and f.alt not in covered and f.alt not in ident_all:
            warns.append(f"field '{f.alt}' is not placed on any tab")
    return plans, warns


def tab_of_key(plans):
    """key -> list of tab names that carry the key (identity keys appear on several tabs)."""
    out = {}
    for p in plans:
        for c in p.columns:
            out.setdefault(c.key, []).append(p.name)
    return out
