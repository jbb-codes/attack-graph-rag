"""Command-line lookup of ATT&CK techniques and groups."""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from importlib.resources import as_file, files
from pathlib import Path

from attack_graph.answer import Answer, Answerer
from attack_graph.graph import AttackGraph, DataFileError, Group, Ref, Technique
from attack_graph.config import ConfigError, build_llm, load_llm_settings
from attack_graph.llm import LLM
from attack_graph.vector import ChromaVectorStore, Embed, VectorStoreError, default_embed
from attack_graph.release import (
    PINNED,
    Fetch,
    Release,
    ReleaseError,
    ensure_downloaded,
    http_fetch,
    write_atomically,
)

DATA_DIR = Path("data")
STORE = DATA_DIR / "attack-graph.nt"
VECTOR_DIR = DATA_DIR / "chroma"


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Fetch = http_fetch,
    release: Release = PINNED,
    embed: Embed = default_embed,
    llm: LLM | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "load":
        return _run_load(release, fetch)

    if args.command == "ask" and llm is None:
        # Fail fast, before touching any data, if the model is not configured.
        try:
            llm = build_llm(load_llm_settings(os.environ if env is None else env))
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2

    if args.command == "search":
        try:
            hits = ChromaVectorStore(VECTOR_DIR, embed).search(args.question, args.limit)
        except VectorStoreError as exc:
            print(exc, file=sys.stderr)
            return 2
        for hit in hits:
            print(f"{hit.attack_id} {hit.name}")
        return 0

    try:
        graph = _load(args.data)
    except DataFileError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "index":
        store = ChromaVectorStore(VECTOR_DIR, embed)
        docs = graph.technique_docs()
        store.index(docs)
        print(f"Indexed {len(docs)} techniques into {VECTOR_DIR}")
        return 0
    if args.command == "ask":
        return _run_ask(args.question, graph, embed, llm)
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
    parser.add_argument("--data", help="STIX JSON file to use (default: data loaded by 'load', else bundled test fixture)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("load", help="download the pinned ATT&CK Enterprise release and load it")
    sub.add_parser("index", help="embed every technique so 'search' can find them by meaning")
    search = sub.add_parser("search", help="find techniques by meaning, e.g. 'how do attackers use email?'")
    search.add_argument("question")
    search.add_argument("--limit", type=int, default=5, help="how many techniques to show (default 5)")
    sub.add_parser("ask", help="answer a question using techniques and graph facts").add_argument("question")
    sub.add_parser("technique", help="look up a technique by ID, e.g. T1566.001").add_argument("id")
    sub.add_parser("group", help="look up a group by name or alias, e.g. APT29").add_argument("name")
    return parser


def _run_ask(question: str, graph: AttackGraph, embed: Embed, llm: LLM) -> int:
    answerer = Answerer(ChromaVectorStore(VECTOR_DIR, embed), graph, llm)
    try:
        answer = answerer.ask(question)
    except VectorStoreError as exc:
        print(exc, file=sys.stderr)
        return 2
    if answer.status in ("invalid", "error"):
        print(answer.text, file=sys.stderr)
        return 2
    print(_format_answer(answer))
    return 0 if answer.status == "answered" else 1


def _format_answer(answer: Answer) -> str:
    if answer.status != "answered":
        return answer.text
    lines = [answer.text, "", "Cited:"]
    lines += [f"  {ref.attack_id} {ref.name}" for ref in answer.cited]
    lines += ["Retrieved:"]
    lines += [f"  {ref.attack_id} {ref.name}" for ref in answer.retrieved]
    return "\n".join(lines)


def _run_load(release: Release, fetch: Fetch) -> int:
    try:
        source = ensure_downloaded(release, DATA_DIR, fetch)
        graph = AttackGraph.from_stix_file(source)
    except (ReleaseError, DataFileError) as exc:
        print(exc, file=sys.stderr)
        return 2
    # Rebuilt from scratch each run, so facts can never pile up as duplicates.
    write_atomically(STORE, graph.to_ntriples())
    print(f"Loaded ATT&CK Enterprise {release.version} into {STORE}")
    return 0


def _load(data: str | None) -> AttackGraph:
    if data is not None:
        return AttackGraph.from_stix_file(data)
    if STORE.exists():
        try:
            return AttackGraph.from_store(STORE)
        except DataFileError as exc:
            raise DataFileError(f"{exc}. Run 'attack-graph load' to rebuild it.") from exc
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
