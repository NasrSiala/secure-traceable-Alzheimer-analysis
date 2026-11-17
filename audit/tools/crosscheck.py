"""Audit helper: markdown link check + ID-reference census for the spec suite."""

import collections
import pathlib
import re

root = pathlib.Path(".")
md = [
    p
    for p in list(root.glob("docs/specs/*.md"))
    + [root / "AGENTS.md", root / "PROGRESS.md", root / "Projet 1.md"]
]


def slug(h):
    h = h.strip().lower()
    h = re.sub(r"[`*_~]", "", h)
    h = re.sub(r"[^\w\s\-àâäçéèêëîïôöùûüÿœæ§.]", "", h)
    h = h.replace(".", "").replace("§", "")
    return re.sub(r"\s", "-", h)


anchors = {}
for p in md:
    t = p.read_text(encoding="utf-8")
    anchors[p.resolve()] = {
        slug(m.group(2)) for m in re.finditer(r"^(#{1,6})\s+(.*)$", t, re.MULTILINE)
    }
bad = []
for p in md:
    t = p.read_text(encoding="utf-8")
    for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", t):
        url = m.group(1)
        if url.startswith(("http://", "https://", "mailto:")):
            continue
        path, _, frag = url.partition("#")
        target = (p.parent / path).resolve() if path else p.resolve()
        if not target.exists():
            bad.append((str(p), url, "MISSING FILE"))
            continue
        if (
            frag
            and target.suffix == ".md"
            and slug(frag) not in anchors.get(target, set())
            and frag not in anchors.get(target, set())
        ):
            bad.append((str(p), url, "anchor?"))
for b in bad:
    print("LINK", *b)
print("links checked; problems:", len(bad))
# ID census
pat = re.compile(
    r"\b(US|AC|NFR|SVC|IF|ADR|DF|FM|E|D|Q|A|F|J|R|T)-(?:[A-Za-z]+[-A-Za-z0-9_]*|\d+(?:[.\-]\d+)*[ab]?)"
)
cnt = collections.defaultdict(set)
for p in md:
    t = p.read_text(encoding="utf-8")
    for m in pat.finditer(t):
        cnt[m.group(0).rstrip(".-")].add(p.name)
once = sorted(k for k, v in cnt.items() if len(v) == 1)
print("IDs seen in only one file (", len(once), "):")
print(", ".join(once))
