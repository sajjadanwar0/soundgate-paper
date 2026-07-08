#!/usr/bin/env python3
"""mediation_lint.py -- best-effort static check for unmediated effect calls.

Complete mediation (every side-effecting tool path traverses the SoundGate
wrapper) is an integration contract the gate cannot enforce from outside.
This linter narrows the bypass risk mechanically: given (a) the names of
side-effecting functions ("effects") and (b) the name of the sanctioned
wrapper, it walks a codebase's ASTs and flags every call site of an effect
that is not lexically inside the wrapper. It is a placement-discipline aid,
NOT a guarantee: dynamic dispatch, getattr, eval, subprocess, and
network calls made by third-party libraries are invisible to it. Pair it
with a structural mechanism (framework choke-point wrapping, or
network-namespace egress allow-listing to the gate host) for defense in
depth.

Usage:
  python3 mediation_lint.py --wrapper mediated_call --effects send_email,charge_card,drop_table src/

Exit status: number of unmediated call sites found (0 = clean).
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def lint_file(path: Path, effects: set[str], wrapper: str) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [f"{path}: unparseable ({e.__class__.__name__}); review manually"]

    findings: list[str] = []
    # Records enclosing function names so calls inside the wrapper are allowed.
    stack: list[str] = []

    class V(ast.NodeVisitor):
        def _visit_fn(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = _visit_fn
        visit_AsyncFunctionDef = _visit_fn

        def visit_Call(self, node: ast.Call):
            name = call_name(node)
            if name in effects and wrapper not in stack:
                findings.append(
                    f"{path}:{node.lineno}: effect `{name}` called outside "
                    f"`{wrapper}` (unmediated path)"
                )
            self.generic_visit(node)

    V().visit(tree)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrapper", required=True,
                    help="name of the sanctioned gate wrapper function")
    ap.add_argument("--effects", required=True,
                    help="comma-separated side-effecting function names")
    ap.add_argument("roots", nargs="+", help="files or directories to scan")
    args = ap.parse_args()

    effects = {e.strip() for e in args.effects.split(",") if e.strip()}
    files: list[Path] = []
    for root in map(Path, args.roots):
        files.extend([root] if root.is_file() else sorted(root.rglob("*.py")))

    findings: list[str] = []
    for f in files:
        findings.extend(lint_file(f, effects, args.wrapper))

    for line in findings:
        print(line)
    print(f"mediation_lint: {len(findings)} unmediated call site(s) "
          f"across {len(files)} file(s)", file=sys.stderr)
    return min(len(findings), 125)


if __name__ == "__main__":
    raise SystemExit(main())
