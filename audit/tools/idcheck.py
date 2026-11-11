import collections
import pathlib
import re

files = list(pathlib.Path("docs/specs").glob("*.md")) + [
    pathlib.Path("AGENTS.md"),
    pathlib.Path("PROGRESS.md"),
]
pat = r"(?:US|AC|NFR|SVC|IF|ADR|DF|FM|E|D|Q|A|J|R|F|S|C|I)-[A-Za-z0-9][A-Za-z0-9_.\-]*"
defs = collections.defaultdict(set)
refs = collections.defaultdict(set)
for p in files:
    for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        d = set()
        m = re.match(r"^\|\s*(?:~~)?\*{0,2}(" + pat + r")", s)
        if m:
            d.add(m.group(1).rstrip(".-"))
        m = re.match(r"^#+\s+.*?\b(" + pat + r")", s)
        if m:
            d.add(m.group(1).rstrip(".-"))
        m = re.match(r"^[-*]\s+\*\*(" + pat + r")", s)
        if m:
            d.add(m.group(1).rstrip(".-"))
        for x in d:
            defs[x].add(p.name)
        for m in re.finditer(r"\b(" + pat + r")", s):
            x = m.group(1).rstrip(".-:,;)")
            refs[x].add((p.name, ln))
und = {k: v for k, v in refs.items() if k not in defs}
# group by prefix
byp = collections.defaultdict(list)
for k in sorted(und):
    byp[k.split("-")[0]].append(k)
for pfx, ks in sorted(byp.items()):
    print(pfx, len(ks), " ".join(ks[:60]))
