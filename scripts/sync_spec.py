#!/usr/bin/env python3
"""Generate ``3dm_spec.json`` from a checkout of tdeck/3dmake.

The spec is derived statically (``ast``) from the 3dmake source so the GUI never
relies on a hand-maintained list of verbs and flags::

    python scripts/sync_spec.py /path/to/3dmake            # rewrite the spec
    python scripts/sync_spec.py /path/to/3dmake --check    # exit 1 on drift

Sources parsed:

* ``actions/__init__.py``  -> action order
* ``actions/*.py``         -> decorators (isolated/pipeline/internal) and their flags
* ``3dm.py``               -> argparse options
* ``coretypes.py``         -> ``CommandOptions`` config keys and defaults
* ``utils/renderer.py``, ``actions/image_action.py``, ``utils/scad_snippets.py``
                           -> enumerations (angles, colour schemes, silhouette views)
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[1] / "src" / "tdmake_gui_wrapper" / "data" / "3dm_spec.json"
DECORATORS = {"isolated_action", "pipeline_action", "internal_action"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _decorator_info(fn: ast.FunctionDef) -> tuple[str, dict[str, ast.AST]] | None:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in DECORATORS:
            return dec.id, {}
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id in DECORATORS:
            return dec.func.id, {kw.arg: kw.value for kw in dec.keywords if kw.arg}
    return None


STDIN_CALLS = {"prompt", "yes_or_no", "option_select", "option_select_with_current", "input"}
EDITOR_CALLS = {"launch_editor"}


def _called_names(fn: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _transitive_calls(module: ast.Module, fn: ast.FunctionDef) -> set[str]:
    """Names called by ``fn`` including helpers defined in the same module."""
    local = {n.name: n for n in module.body if isinstance(n, ast.FunctionDef)}
    seen: set[str] = set()
    todo = [fn.name]
    out: set[str] = set()
    while todo:
        cur = todo.pop()
        if cur in seen or cur not in local:
            continue
        seen.add(cur)
        calls = _called_names(local[cur])
        out |= calls
        todo.extend(c for c in calls if c in local)
    return out


def parse_actions(root: Path) -> list[dict]:
    by_func: dict[str, dict] = {}
    for path in sorted((root / "actions").glob("*_action*.py")) + [root / "actions" / "edit_actions.py"]:
        if not path.exists():
            continue
        module = _parse(path)
        for node in module.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            info = _decorator_info(node)
            if not info:
                continue
            kind, kw = info
            name = _literal(kw["name"]) if "name" in kw else node.name.replace("_", "-")
            doc = ast.get_docstring(node)
            implied = []
            if "implied_actions" in kw and isinstance(kw["implied_actions"], ast.List):
                implied = [e.id for e in kw["implied_actions"].elts if isinstance(e, ast.Name)]
            is_pipeline = kind in {"pipeline_action", "internal_action"}
            entry = {
                "name": name,
                "function": node.name,
                "kind": {"isolated_action": "isolated", "pipeline_action": "pipeline", "internal_action": "internal"}[kind],
                "doc": doc.strip().splitlines()[0].strip() if doc else None,
                "isolated": kind == "isolated_action",
                "internal": kind == "internal_action",
                "needs_options": True if is_pipeline else bool(_literal(kw.get("needs_options", ast.Constant(False)))),
                "uses_project_files": True if is_pipeline else bool(_literal(kw.get("uses_project_files", ast.Constant(False)))),
                "input_file_types": _literal(kw.get("input_file_types", ast.List([], ast.Load()))) or [],
                "last_in_chain": bool(_literal(kw.get("last_in_chain", ast.Constant(False)))),
                "reads_stdin": bool(_transitive_calls(module, node) & STDIN_CALLS),
                "launches_editor": bool(_transitive_calls(module, node) & EDITOR_CALLS),
                "_implied_funcs": implied,
                "source": f"actions/{path.name}",
            }
            by_func[node.name] = entry
    # resolve implied function names -> action names
    for entry in by_func.values():
        entry["implied_actions"] = [by_func[f]["name"] for f in entry.pop("_implied_funcs") if f in by_func]
    return list(by_func.values()), by_func


def parse_order(root: Path, by_func: dict[str, dict]) -> list[str]:
    tree = _parse(root / "actions" / "__init__.py")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_actions_in_order" for t in node.targets):
            return [by_func[e.attr]["name"] for e in node.value.elts if isinstance(e, ast.Attribute) and e.attr in by_func]
    raise SystemExit("could not find _actions_in_order in actions/__init__.py")


def parse_options(root: Path) -> list[dict]:
    options = []
    for node in ast.walk(_parse(root / "3dm.py")):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.func.value.id == "parser"
        ):
            flags = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if not flags or not flags[0].startswith("-"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            action = _literal(kw["action"]) if "action" in kw and isinstance(kw["action"], ast.Constant) else None
            takes_value = action not in {"store_true"} and not (
                isinstance(kw.get("action"), ast.Name) and "nargs" in kw and _literal(kw["nargs"]) == 0
            )
            options.append(
                {
                    "flags": flags,
                    "dest": next((f for f in flags if f.startswith("--")), flags[0]).lstrip("-").replace("-", "_"),
                    "takes_value": bool(takes_value),
                    "repeatable": action == "extend",
                    "type": ast.unparse(kw["type"]) if "type" in kw else "str",
                }
            )
    return options


def parse_config_keys(root: Path) -> list[dict]:
    for node in _parse(root / "coretypes.py").body:
        if isinstance(node, ast.ClassDef) and node.name == "CommandOptions":
            keys = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    default = None
                    required = stmt.value is None
                    if stmt.value is not None:
                        if isinstance(stmt.value, ast.Call):
                            for kw in stmt.value.keywords:
                                if kw.arg == "default_factory":
                                    try:
                                        default = _literal(kw.value.body) if isinstance(kw.value, ast.Lambda) else []
                                    except Exception:
                                        default = None
                        else:
                            default = _literal(stmt.value)
                    keys.append(
                        {"key": stmt.target.id, "type": ast.unparse(stmt.annotation), "default": default, "required": required}
                    )
            return keys
    return []


def dict_keys(path: Path, var: str) -> list[str]:
    for node in _parse(path).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == var for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return []


def build_spec(root: Path) -> dict:
    actions, by_func = parse_actions(root)
    order = parse_order(root, by_func)
    ordered = sorted(
        [a for a in actions if a["name"] in order],
        key=lambda a: order.index(a["name"]),
    )
    return {
        "generated_by": "scripts/sync_spec.py",
        "source": "tdeck/3dmake (AST-derived; do not edit by hand)",
        "action_order": order,
        "actions": ordered,
        "options": parse_options(root),
        "config_keys": parse_config_keys(root),
        "enums": {
            "image_angles": dict_keys(root / "utils" / "renderer.py", "VIEWPOINTS"),
            "colorschemes": dict_keys(root / "actions" / "image_action.py", "COLORSCHEMES"),
            "silhouette_views": dict_keys(root / "utils" / "scad_snippets.py", "NAMED_PROJECTION_CODE"),
            "print_modes": ["octoprint", "bambu_lan", "bambu_connect"],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="path to a tdeck/3dmake checkout")
    ap.add_argument("--check", action="store_true", help="fail if the committed spec differs")
    ap.add_argument("--out", type=Path, default=SPEC_PATH)
    args = ap.parse_args()

    text = json.dumps(build_spec(args.root), indent=2) + "\n"
    if args.check:
        if not args.out.exists() or args.out.read_text(encoding="utf-8") != text:
            print("3dm spec drift detected; run scripts/sync_spec.py", file=sys.stderr)
            return 1
        print("spec up to date")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
