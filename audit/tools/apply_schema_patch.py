"""Apply the approved least-privilege patch (AUD-002, AUD-008, AUD-009) and bump to suite v2.1.2.
All-or-nothing: every replacement must match exactly once. CRLF preserved."""

import pathlib
import sys

edits = {}


def E(path, old, new, count=1):
    edits.setdefault(path, []).append((old, new, count))


S = "docs/specs/"
sql = S + "schema.sql"
E(
    sql,
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_api, app_worker;\n",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_api, app_worker;\n"
    "-- le worker ne lit ni les comptes, ni les jetons de rafraîchissement, ni les tentatives de connexion\n"
    "REVOKE SELECT ON users, refresh_tokens, login_attempts FROM app_worker;\n",
)
E(
    sql,
    "GRANT INSERT, UPDATE         ON users, validation_configs           TO app_api;\n",
    "GRANT INSERT, UPDATE         ON users                               TO app_api;\n"
    "GRANT INSERT                 ON validation_configs                  TO app_api;   -- lignes jamais modifiées (Schema §5.1)\n"
    "GRANT UPDATE (is_active)     ON validation_configs                  TO app_api;   -- scripts/registry.py config activate\n",
)
old_la = "GRANT DELETE                 ON cases                               TO app_api;   -- purge admin (cascade)\n"
E(
    sql,
    old_la,
    old_la
    + "GRANT DELETE                 ON login_attempts                      TO app_api;   -- rétention 30 jours (Schema §16)\n",
)
E(
    sql,
    "GRANT INSERT, UPDATE         ON artifacts                           TO app_worker;\n",
    "GRANT INSERT                 ON artifacts                           TO app_worker;\n"
    "GRANT UPDATE (anchor_status, anchor_attempts, tx_id, anchored_at)\n"
    "                             ON artifacts                           TO app_worker;   -- sha256, type, parent jamais modifiés (Schema §10)\n",
)
E(
    sql,
    "(Backend Schema v2.0.2, suite v2.1.1, 2026-11-09 — DDL inchangé depuis la v1.0.0)",
    "(Backend Schema v2.0.3, suite v2.1.2, 2026-11-09 — tables, colonnes et contraintes inchangées depuis la v1.0.0 ; privilèges resserrés)",
)

# versions
E(
    S + "04-backend-schema.md",
    "| 2.0.2 | 2026-11-09 | 2.1.1 |",
    "| 2.0.3 | 2026-11-09 | 2.1.2 |",
)
P = S + "08-implementation-plan.md"
E(P, "| 2.1.1 | 2026-11-09 | 2.1.1 |", "| 2.1.2 | 2026-11-09 | 2.1.2 |")
E(P, "[schema.sql](schema.sql) | 2.0.2 |", "[schema.sql](schema.sql) | 2.0.3 |")
E(P, "| [review.md](review.md) | 2.1.1 |", "| [review.md](review.md) | 2.1.2 |")
E(P, "| [aar.md](aar.md) | 2.1.1 |", "| [aar.md](aar.md) | 2.1.2 |")
E(
    "AGENTS.md",
    "Suite de specs v2.1.1 (8 documents)",
    "Suite de specs v2.1.2 (8 documents)",
)
E(
    "PROGRESS.md",
    "Suite de specs : v2.1.1 (2026-11-09)",
    "Suite de specs : v2.1.2 (2026-11-09)",
)
# 5 headers were corrupted to "22.1.1" by an off-by-one in the v2.1.1 pass; repaired here.
for f, old in [
    ("01-prd.md", "| 2.0.1 | 2026-10-23 | 22.1.1 |"),
    ("03-architecture.md", "| 1.0.1 | 2026-10-23 | 22.1.1 |"),
    ("06-app-flow.md", "| 2.0.2 | 2026-11-09 | 22.1.1 |"),
    ("07-design-brief.md", "| 2.0.1 | 2026-10-23 | 22.1.1 |"),
    ("08-implementation-plan-L.md", "| 1.0.0 | 2026-11-09 | 22.1.1 |"),
]:
    E(S + f, old, old.replace("22.1.1", "2.1.2"))
for f, old in [
    ("02-trd.md", "| 2.0.3 | 2026-11-09 | 2.1.1 |"),
    ("05-system-design.md", "| 1.0.2 | 2026-11-09 | 2.1.1 |"),
]:
    E(S + f, old, old.replace("2.1.1", "2.1.2"))
for f in ("aar.md", "review.md", "traceability.md"):
    E(S + f, "Suite version : 2.1.1 —", "Suite version : 2.1.2 —")
E(
    S + "review.md",
    "| Même version de suite sur tous les documents | ✓ 2.1.1 |",
    "| Même version de suite sur tous les documents | ✓ 2.1.2 |",
)

# CHANGELOG entry
cl = S + "CHANGELOG.md"
anchor = "## Suite v2.1.1 — 2026-11-09\n"
entry = """## Suite v2.1.2 — 2026-11-09
**Change:** moindre privilège des rôles de base dans `schema.sql`, décidé après l'audit de code (`audit/AUDIT_REPORT.md`).  **Requested by:** utilisateur  **Decision:** accord de l'utilisateur, 2026-11-09  **From audit:** AUD-002, AUD-008, AUD-009

- Backend Schema v2.0.3 : `schema.sql`, section des privilèges seulement — `app_worker` ne lit plus `users`, `refresh_tokens`, `login_attempts` ; `UPDATE` par colonnes sur `validation_configs` (`is_active`) et sur `artifacts` (`anchor_status`, `anchor_attempts`, `tx_id`, `anchored_at`), conformément à Schema §5.1 et §10 ; `app_api` peut supprimer dans `login_attempts` (rétention 30 jours, Schema §16). Tables, colonnes, contraintes et index inchangés : traité en correctif car aucun consommateur n'existe encore et les règles écrites du Schema §10 et §16 sont désormais appliquées par la base. Vérifié sur PostgreSQL 16 : 23 contrôles de privilèges passent (`audit/tools/verify_schema_patch.sh`).
- Plan v2.1.2 : §1, versions recalées. Version de suite dans les en-têtes de tous les documents, AGENTS.md et PROGRESS.md : 2.1.2. Autres documents inchangés sur le fond.
- Pour T2.1 : la migration Alembic initiale doit reproduire ces privilèges (`tests/db/test_grants.py`, T1.11).

"""
E(cl, anchor, entry + anchor)

# PROGRESS: remove open item, add decision
pg = "PROGRESS.md"
loaded = {}
for path, lst in edits.items():
    raw = pathlib.Path(path).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    for old, new, count in lst:
        n = text.count(old)
        if n != count:
            sys.exit(f"ABORT {path}: expected {count}, found {n}: {old[:70]!r}")
        text = text.replace(old, new)
    loaded[path] = (text, crlf)
text, crlf = loaded[pg]
i = text.index("| 2026-11-09 | Moindre privilège de `schema.sql`")
j = text.index("\n", i) + 1
text = text[:i] + text[j:]
dec_anchor = "\n## Problèmes\n"
assert text.count(dec_anchor) == 1
row = "| 2026-11-09 | Moindre privilège des rôles de base (`schema.sql`, suite v2.1.2) : `app_worker` sans lecture des comptes, `UPDATE` par colonnes sur `artifacts` et `validation_configs`, `DELETE` sur `login_attempts` pour `app_api` | Constats AUD-002, AUD-008, AUD-009 de l'audit ; accord de l'utilisateur | Oui : schema.sql, 04-backend-schema.md, CHANGELOG. T2.1 devra reproduire ces privilèges |\n"
k = text.index(dec_anchor)
# insert row at end of the Décisions table (just before the blank line preceding '## Problèmes')
text = text[:k].rstrip("\n") + "\n" + row + text[k:]
loaded[pg] = (text, crlf)
for path, (text, crlf) in loaded.items():
    pathlib.Path(path).write_bytes(
        (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
    )
print("applied to", len(loaded), "files")
