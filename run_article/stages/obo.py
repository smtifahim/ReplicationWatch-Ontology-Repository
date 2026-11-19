"""Small OBO loader: labels, synonyms with scope, parents (is_a and part_of), obsolete terms skipped.
Not OAK. It is the lightweight exact-match loader used in the proof of concept, kept here so the run needs no extra install."""
import collections, hashlib, re


class Obo:
    def __init__(self, path, prefix):
        self.path, self.prefix = path, prefix
        self.name, self.parents, self.syn = {}, collections.defaultdict(set), {}
        self.xref = collections.defaultdict(list)      # id -> [(xref id, qualifier text)]
        self.idx = collections.defaultdict(list)       # lowercased string -> [(id, match_type, original string)]
        self.header = {}
        self._load()
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        self.sha256 = h
        self.version = self.header.get("data-version") or self.header.get("date") or ("sha256:" + h[:12])

    def _load(self):
        cur, in_header = None, True
        for line in open(self.path, encoding="utf-8"):
            line = line.rstrip("\n")
            if line.startswith("["):
                in_header = False
                cur = {"id": None, "name": None, "syn": [], "par": set(), "obs": False, "xref": []} if line == "[Term]" else None
                continue
            if in_header:
                if ": " in line:
                    k, v = line.split(": ", 1); self.header.setdefault(k, v)
                continue
            if cur is None:
                continue
            if line == "":
                self._commit(cur); cur = None; continue
            if line.startswith("id: "): cur["id"] = line[4:]
            elif line.startswith("name: "): cur["name"] = line[6:]
            elif line.startswith("is_obsolete: true"): cur["obs"] = True
            elif line.startswith("xref: "):
                x = line[6:].split(" ", 1); cur["xref"].append((x[0], x[1] if len(x) > 1 else ""))
            elif line.startswith("is_a: "): cur["par"].add(line[6:].split(" ")[0])
            elif line.startswith("relationship: part_of "): cur["par"].add(line.split(" ")[2])
            elif line.startswith("synonym: "):
                m = re.match(r'synonym: "(.*?)" (\w+)', line)
                if m: cur["syn"].append((m.group(1), m.group(2)))
        if cur: self._commit(cur)

    def _commit(self, c):
        if not (c["id"] and c["name"] and c["id"].startswith(self.prefix)) or c["obs"]:
            return
        self.name[c["id"]] = c["name"]
        self.xref[c["id"]] = c["xref"]
        self.parents[c["id"]] = {p for p in c["par"] if p.startswith(self.prefix)}
        self.idx[c["name"].lower()].append((c["id"], "label", c["name"]))
        for s, sc in c["syn"]:
            self.idx[s.lower()].append((c["id"], sc, s))

    def look(self, term):
        return self.idx.get(term.lower().strip(), [])

    def exact(self, term):
        """Single id reached by label or EXACT synonym, else None. Also returns a status string."""
        hits = self.look(term)
        exact_ids = sorted({h[0] for h in hits if h[1] in ("label", "EXACT")})
        if len(exact_ids) == 1:
            h = [x for x in hits if x[0] == exact_ids[0] and x[1] in ("label", "EXACT")][0]
            return exact_ids[0], "matched", h
        if len(exact_ids) > 1:
            return None, "ambiguous", [h for h in hits if h[1] in ("label", "EXACT")]
        if hits:
            return None, "related_only", hits
        return None, "none", []

    def ancestors(self, tid):
        seen, stack = set(), [tid]
        while stack:
            t = stack.pop()
            for p in self.parents.get(t, ()):
                if p not in seen and p in self.name:
                    seen.add(p); stack.append(p)
        return seen

    def suggest(self, term, k=5):
        """Advisory near-matches by token overlap with labels and EXACT synonyms. Never applied."""
        stop = {"of", "the", "and", "a", "an", "in", "part"}
        toks = lambda s: {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in stop}
        q = toks(term)
        if not q: return []
        def scan(min_inter):
            out = []
            for key, hits in self.idx.items():
                t = toks(key)
                inter = len(q & t)
                if not t or inter < min_inter: continue
                jac = inter / len(q | t)
                for h in hits:
                    if h[1] in ("label", "EXACT"):
                        out.append((jac, h[0], self.name[h[0]], h[2]))
            return out
        scored = scan(max(1, min(len(q), 2))) or scan(1)
        best = {}
        for jac, i, n, s in sorted(scored, reverse=True):
            best.setdefault(i, (jac, i, n, s))
        return [dict(curie=i, label=n, via=s, score=round(j, 2)) for j, i, n, s in list(best.values())[:k]]
