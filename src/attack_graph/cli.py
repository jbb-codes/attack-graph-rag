"""Command-line lookup of ATT&CK techniques and groups."""

import argparse
import sys
from collections.abc import Sequence
from importlib.resources import as_file, files

from attack_graph.graph import AttackGraph, DataFileError, Group, Ref, Technique


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        graph = _load(args.data)
    except DataFileError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "technique":
        technique = graph.technique(args.id)
        if technique is None:
            print(f"No technique found with ID {args.id.strip()!r}.", file=sys.stderr)
            return 1
        print(_format_technique(technique))
    else:
        group = graph.group(args.name)
        if group is None:
            print(f"No group found named {args.name.strip()!r}.", file=sys.stderr)
            return 1
        print(_format_group(group))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="attack-graph", description="Look up MITRE ATT&CK facts.")
    parser.add_argument("--data", help="STIX JSON file to load (default: bundled test fixture)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("technique", help="look up a technique by ID, e.g. T1566.001").add_argument("id")
    sub.add_parser("group", help="look up a group by name or alias, e.g. APT29").add_argument("name")
    return parser


def _load(data: str | None) -> AttackGraph:
    if data is not None:
        return AttackGraph.from_stix_file(data)
    with as_file(files("attack_graph") / "data" / "attack_fixture.json") as path:
        return AttackGraph.from_stix_file(path)


def _refs(label: str, refs: tuple[Ref, ...]) -> str:
    if not refs:
        return f"{label}: none"
    lines = "\n".join(f"  {ref.attack_id} {ref.name}" for ref in refs)
    return f"{label}:\n{lines}"


def _format_technique(t: Technique) -> str:
    return "\n".join([
        f"{t.attack_id} {t.name}",
        f"Tactics: {', '.join(t.tactics) or 'none'}",
        t.description,
        "",
        _refs("Groups", t.groups),
        _refs("Software", t.software),
        _refs("Mitigations", t.mitigations),
    ])


def _format_group(g: Group) -> str:
    return "\n".join([
        f"{g.attack_id} {g.name}",
        f"Aliases: {', '.join(g.aliases) or 'none'}",
        g.description,
        "",
        _refs("Techniques", g.techniques),
        _refs("Software", g.software),
    ])
