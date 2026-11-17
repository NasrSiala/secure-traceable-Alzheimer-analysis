"""Analyse statique des imports et des accès SQL du squelette courant.

Les requêtes exécutées doivent être des littéraux, des constantes ou des
concaténations résolubles. Les expressions ORM demanderont leur contrôle de
liaison aux modèles lorsque ces expressions seront introduites.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TABLE_OWNERS = {
    "users": "identity",
    "refresh_tokens": "identity",
    "login_attempts": "identity",
    "cases": "cases",
    "jobs": "cases",
    "models": "registry",
    "validation_configs": "registry",
    "artifacts": "traceability",
    "artifact_files": "traceability",
    "agent_logs": "pipeline",
    "verifications": "verification",
    "verification_items": "verification",
    "audit_events": "audit",
}

# Diagramme §5 et consommateurs explicites des interfaces §7/§8.
DEPENDENCIES = {
    "api": {
        "identity",
        "cases",
        "registry",
        "traceability",
        "verification",
        "audit",
        "ledger",
    },
    "pipeline": {"cases", "registry", "traceability", "verification", "dsp", "audit"},
    "registry": {"hashing", "ledger"},
    "traceability": {"hashing", "ledger", "audit", "storage"},
    "verification": {"cases", "traceability", "hashing", "ledger"},
    "identity": set(),
    "cases": set(),
    "audit": set(),
    "hashing": set(),
    "dsp": set(),
    "ledger": set(),
    "storage": set(),
}
FORBIDDEN_EXTERNAL = {"hw", "serial", "pyserial", "hfc", "grpc", "fabric_sdk_py"}


def is_logs(module: str) -> bool:
    return module == "saam.pipeline.logs" or module.startswith("saam.pipeline.logs.")


def modules(root: Path) -> list[tuple[str, str]]:
    return [
        (
            ".".join(path.relative_to(root).with_suffix("").parts),
            path.read_text(encoding="utf-8"),
        )
        for path in sorted((root / "saam").rglob("*.py"))
    ]


def imports(tree: ast.AST, module: str) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = module.split(".")[: -node.level]
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            found.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            argument = node.args[0]
            if (
                name in {"__import__", "import_module"}
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                found.add(argument.value)
    return found


def import_violations(source: str, module: str) -> list[str]:
    owner = module.split(".")[1]
    errors = []
    for target in sorted(imports(ast.parse(source), module)):
        parts = target.split(".")
        if parts[0] in FORBIDDEN_EXTERNAL:
            errors.append(f"{module} importe {target}, interdit par ADR-16/IF-09")
        if parts[0] != "saam" or len(parts) < 2:
            continue
        other = parts[1]
        if is_logs(module) and other == "pipeline" and not is_logs(target):
            errors.append(
                f"{module} doit rester une interface de lecture indépendante du pipeline"
            )
        if other == owner:
            continue
        if owner == "api" and is_logs(target):
            continue
        if other not in DEPENDENCIES.get(owner, set()):
            errors.append(
                f"{module} ne doit pas importer {target} (Architecture §5–§8)"
            )
        elif len(parts) > 2 and parts[2] == "models":
            errors.append(
                f"{module} accède aux modèles ORM de {other} au lieu de son interface"
            )
    return errors


def literal(
    node: ast.AST, bindings: dict[str, ast.AST], seen: frozenset[str] = frozenset()
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in bindings and node.id not in seen:
        return literal(bindings[node.id], bindings, seen | {node.id})
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = (
            literal(node.left, bindings, seen),
            literal(node.right, bindings, seen),
        )
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else "{}"
            for part in node.values
        )
    if (
        isinstance(node, ast.Call)
        and node.args
        and getattr(node.func, "attr", getattr(node.func, "id", "")) in {"text", "SQL"}
    ):
        return literal(node.args[0], bindings, seen)
    return None


IDENTIFIER = r'"?[a-zA-Z_][a-zA-Z_0-9]*"?(?:\s*\.\s*"?[a-zA-Z_][a-zA-Z_0-9]*"?)?'
OPERATIONS = r"INSERT\s+INTO|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?|UPDATE|FROM|JOIN|USING|(?:CREATE|ALTER|DROP)\s+TABLE"
ACCESS = re.compile(
    rf"\b({OPERATIONS})(?:\s+IF(?:\s+NOT)?\s+EXISTS)?\s+({IDENTIFIER})", re.I
)
DYNAMIC_ACCESS = re.compile(rf"\b(?:{OPERATIONS})\s+(?:[\w\".]+\s*)?\{{\}}", re.I)


def table_violations(source: str, module: str) -> list[str]:
    tree = ast.parse(source)
    owner = module.split(".")[1]
    bindings = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__tablename__"
            for target in node.targets
        ):
            table = literal(node.value, bindings)
            if TABLE_OWNERS.get(table or "") != owner:
                errors.append(
                    f"{module} déclare une table étrangère ou inconnue : {table}"
                )
        if (
            not isinstance(node, ast.Call)
            or getattr(node.func, "attr", "") not in {"execute", "executemany"}
            or not node.args
        ):
            continue
        query = literal(node.args[0], bindings)
        if query is None:
            errors.append(
                f"{module}:{node.lineno} requête SQL non résoluble ; déclarer son accès aux tables"
            )
            continue
        query = re.sub(r"'(?:''|[^'])*'|--[^\n]*|/\*.*?\*/", " ", query, flags=re.S)
        if DYNAMIC_ACCESS.search(query):
            errors.append(
                f"{module}:{node.lineno} nom de table dynamique non contrôlable"
            )
        references = []
        for match in ACCESS.finditer(query):
            operation, identifier = match.groups()
            references.append((operation, identifier))
            tail = query[match.end() :]
            while extra := re.match(rf"\s*(?:[\w\"]+\s*)?,\s*({IDENTIFIER})", tail):
                references.append((operation, extra[1]))
                tail = tail[extra.end() :]
        for operation, identifier in references:
            parts = identifier.replace('"', "").replace(" ", "").lower().split(".")
            table_owner = (
                "pipeline"
                if len(parts) == 2 and parts[0] == "langgraph"
                else TABLE_OWNERS.get(parts[-1])
            )
            if table_owner is not None and table_owner != owner:
                errors.append(
                    f"{module}:{node.lineno} {operation} {identifier} appartient à {table_owner}"
                )
            if is_logs(module) and operation.upper() not in {
                "FROM",
                "JOIN",
                "USING",
            }:
                errors.append(
                    f"{module}:{node.lineno} l'interface logs est en lecture seule"
                )
    return sorted(set(errors))


def oracle_violations(source: str, module: str) -> list[str]:
    tree = ast.parse(source)
    dependencies = imports(tree, module)
    errors = []
    required = (
        "saam.hashing"
        if "sha256" in module
        else "saam.dsp.fir_fixed"
        if "fir" in module
        else None
    )
    if required and not any(
        path == required or path.startswith(required + ".") for path in dependencies
    ):
        errors.append(f"{module} doit réutiliser l'oracle {required}")
    elif required:
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                aliases.update(
                    (
                        alias.asname or alias.name.split(".")[0],
                        alias.name if alias.asname else alias.name.split(".")[0],
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                aliases.update(
                    (alias.asname or alias.name, f"{node.module}.{alias.name}")
                    for alias in node.names
                )

        def qualified(node: ast.AST) -> str:
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return qualified(node.value) + "." + node.attr
            return ""

        calls = {
            qualified(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        if not any(name.startswith(required + ".") for name in calls):
            errors.append(f"{module} importe l'oracle {required} sans l'appeler")
        if calls & {"scipy.signal.lfilter", "numpy.convolve"}:
            errors.append(
                f"{module} ne doit pas reconstruire une référence FIR avec SciPy/NumPy"
            )
    if any(path == "hashlib" or path.startswith("hashlib.") for path in dependencies):
        errors.append(f"{module} ne doit pas recalculer son oracle avec hashlib")
    duplicates = {
        "canonical_manifest",
        "artifact_hash",
        "file_hash",
        "sha256",
        "filter_decimate",
    }
    if any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in duplicates
        for node in ast.walk(tree)
    ):
        errors.append(f"{module} redéfinit un oracle au lieu de réutiliser saam")
    return errors
