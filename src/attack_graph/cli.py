"""Command-line lookup of ATT&CK techniques and groups."""

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from importlib.resources import as_file, files
from pathlib import Path

from fastapi import FastAPI

from datetime import datetime, timezone

from attack_graph.answer import Answer, Answerer
from attack_graph.evals import EvalError, injection_cases, latest_run, load_cases, run_evals, save_run, summarize
from attack_graph.graph import AttackGraph, DataFileError, Group, Ref, Technique
from attack_graph.security_log import configure_logging
from attack_graph.api import create_app
from attack_graph.config import ConfigError, StoreSettings, build_llm, load_llm_settings, load_store_settings
from attack_graph.sparql import GraphServerError, SparqlServer
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

RunServer = Callable[[FastAPI, str, int], None]


def _uvicorn_run(app: FastAPI, host: str, port: int) -> None:
    # Imported here so other commands never pay for loading the server.
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Fetch = http_fetch,
    release: Release = PINNED,
    embed: Embed = default_embed,
    llm: LLM | None = None,
    env: Mapping[str, str] | None = None,
    run_server: RunServer = _uvicorn_run,
) -> int:
    args = _build_parser().parse_args(argv)
    env = os.environ if env is None else env

    try:
        stores = load_store_settings(env)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "load":
        return _run_load(release, fetch, stores)

    llm_label = type(llm).__name__
    if args.command in ("ask", "serve", "eval") and llm is None:
        # Fail fast, before touching any data, if the model is not configured.
        try:
            settings = load_llm_settings(env)
            llm = build_llm(settings)
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        llm_label = settings.claude_model if settings.provider == "claude" else settings.provider

    if args.command == "search":
        try:
            hits = _vector_store(stores, embed).search(args.question, args.limit)
        except VectorStoreError as exc:
            print(exc, file=sys.stderr)
            return 2
        for hit in hits:
            print(f"{hit.attack_id} {hit.name}")
        return 0

    try:
        graph = _load(args.data, stores)
    except (DataFileError, GraphServerError) as exc:
        print(_with_variable_hint(exc), file=sys.stderr)
        return 2

    if args.command in ("index", "ask", "serve", "eval"):
        try:
            vectors = _vector_store(stores, embed)
        except VectorStoreError as exc:
            print(exc, file=sys.stderr)
            return 2
        if args.command == "ask":
            return _run_ask(args.question, graph, vectors, llm)
        if args.command == "eval":
            return _run_eval(args, Answerer(vectors, graph, llm), llm_label)
        if args.command == "serve":
            configure_logging()
            run_server(create_app(Answerer(vectors, graph, llm)), args.host, args.port)
            return 0
        docs = graph.technique_docs()
        vectors.index(docs)
        print(f"Indexed {len(docs)} techniques")
        return 0
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
    serve = sub.add_parser("serve", help="run the HTTP API (POST /ask, GET /health)")
    # Localhost only by default; exposing it is a deliberate choice.
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    evals = sub.add_parser("eval", help="score the eval questions against the configured model and save the results")
    evals.add_argument("--cases", default="evals/questions.json", help="eval questions (default evals/questions.json)")
    evals.add_argument("--corpus", default="tests/injection_corpus.json", help="injection attacks to add as cases (skipped if missing)")
    evals.add_argument("--results-dir", default="eval-results", help="where results are saved (default eval-results, git-ignored)")
    sub.add_parser("technique", help="look up a technique by ID, e.g. T1566.001").add_argument("id")
    sub.add_parser("group", help="look up a group by name or alias, e.g. APT29").add_argument("name")
    return parser


def _vector_store(stores: StoreSettings, embed: Embed) -> ChromaVectorStore:
    if stores.chroma_url:
        return ChromaVectorStore.remote(stores.chroma_url, embed)
    return ChromaVectorStore(VECTOR_DIR, embed)


def _run_ask(question: str, graph: AttackGraph, vectors: ChromaVectorStore, llm: LLM) -> int:
    answerer = Answerer(vectors, graph, llm)
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


def _run_eval(args: argparse.Namespace, answerer: Answerer, label: str) -> int:
    try:
        cases = load_cases(args.cases) + injection_cases(args.corpus)
        previous = latest_run(args.results_dir)
        run = run_evals(answerer, cases, label=label, now=datetime.now(timezone.utc))
    except (EvalError, VectorStoreError) as exc:
        print(exc, file=sys.stderr)
        return 2
    path = save_run(run, args.results_dir)
    print(summarize(run, previous))
    print(f"Saved {path}")
    return 0 if run.passed == run.total else 1


def _format_answer(answer: Answer) -> str:
    if answer.status != "answered":
        return answer.text
    lines = [answer.text, "", "Cited:"]
    lines += [f"  {ref.attack_id} {ref.name}" for ref in answer.cited]
    lines += ["Retrieved:"]
    lines += [f"  {ref.attack_id} {ref.name}" for ref in answer.retrieved]
    return "\n".join(lines)


def _run_load(release: Release, fetch: Fetch, stores: StoreSettings) -> int:
    try:
        source = ensure_downloaded(release, DATA_DIR, fetch)
        graph = AttackGraph.from_stix_file(source)
        # Rebuilt from scratch each run, so facts can never pile up as duplicates.
        if stores.sparql_url:
            SparqlServer(stores.sparql_url).replace(graph.to_ntriples())
            destination = "the SPARQL server"
        else:
            write_atomically(STORE, graph.to_ntriples())
            destination = str(STORE)
    except (ReleaseError, DataFileError, GraphServerError) as exc:
        print(_with_variable_hint(exc), file=sys.stderr)
        return 2
    print(f"Loaded ATT&CK Enterprise {release.version} into {destination}")
    return 0


def _with_variable_hint(exc: Exception) -> str:
    if isinstance(exc, GraphServerError):
        return f"{exc} Check that the server is running and ATTACK_GRAPH_SPARQL_URL is right."
    return str(exc)


def _load(data: str | None, stores: StoreSettings) -> AttackGraph:
    if data is not None:
        return AttackGraph.from_stix_file(data)
    if stores.sparql_url:
        return SparqlServer(stores.sparql_url).graph()
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
