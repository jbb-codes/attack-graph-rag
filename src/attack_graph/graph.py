"""In-memory RDF graph of ATT&CK data, loaded from a STIX bundle.

RDF stores facts as triples: (subject, predicate, object). Each ATT&CK item
(technique, group, ...) is a subject; its name, ID and links to other items
are predicates and objects. SPARQL is the query language for matching
patterns of triples.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from rdflib import RDF, Graph, Literal, Namespace, URIRef

AG = Namespace("https://attack-graph-rag.example/ns#")

_STIX_KINDS = {
    "attack-pattern": AG.Technique,
    "intrusion-set": AG.Group,
    "malware": AG.Software,
    "tool": AG.Software,
    "course-of-action": AG.Mitigation,
}
_RELATIONS = {"uses": AG.uses, "mitigates": AG.mitigates}


class DataFileError(Exception):
    """The ATT&CK data file is missing or not a valid STIX bundle."""


@dataclass(frozen=True)
class Ref:
    attack_id: str
    name: str


@dataclass(frozen=True)
class Technique:
    attack_id: str
    name: str
    description: str
    tactics: tuple[str, ...]
    groups: tuple[Ref, ...]
    software: tuple[Ref, ...]
    mitigations: tuple[Ref, ...]


@dataclass(frozen=True)
class Group:
    attack_id: str
    name: str
    aliases: tuple[str, ...]
    description: str
    techniques: tuple[Ref, ...]
    software: tuple[Ref, ...]


class AttackGraph:
    def __init__(self, graph: Graph) -> None:
        self._graph = graph

    @classmethod
    def from_stix_file(cls, path: Path | str) -> "AttackGraph":
        try:
            bundle = json.loads(Path(path).read_text(encoding="utf-8"))
            objects = bundle["objects"]
        except OSError as exc:
            raise DataFileError(f"Cannot read data file {path}: {exc.strerror}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DataFileError(f"{path} is not a valid STIX bundle") from exc

        graph = Graph()
        graph.bind("ag", AG)
        known: set[str] = set()
        for obj in objects:
            if _add_object(graph, obj):
                known.add(obj["id"])
        for obj in objects:
            _add_relationship(graph, obj, known)
        return cls(graph)

    @classmethod
    def from_store(cls, path: Path | str) -> "AttackGraph":
        graph = Graph()
        graph.bind("ag", AG)
        try:
            graph.parse(str(path), format="nt")
        except OSError as exc:
            raise DataFileError(f"Cannot read graph store {path}: {exc.strerror}") from exc
        except Exception as exc:  # rdflib raises assorted parser errors
            raise DataFileError(f"{path} is not a valid graph store") from exc
        return cls(graph)

    def to_ntriples(self) -> bytes:
        # Sorted so the same facts always produce the same bytes.
        lines = self._graph.serialize(format="nt").splitlines()
        return ("\n".join(sorted(line for line in lines if line)) + "\n").encode("utf-8")

    def technique(self, attack_id: str) -> Technique | None:
        attack_id = attack_id.strip().upper()
        row = self._first(
            "SELECT ?s ?name ?desc WHERE { ?s a ag:Technique ; ag:attackId ?id ;"
            " ag:name ?name ; ag:description ?desc }",
            id=Literal(attack_id),
        )
        if row is None:
            return None
        subject = row.s
        return Technique(
            attack_id=attack_id,
            name=str(row.name),
            description=str(row.desc),
            tactics=tuple(sorted(str(r.v) for r in self._query(
                "SELECT ?v WHERE { ?s ag:tactic ?v }", s=subject))),
            groups=self._refs("?x a ag:Group ; ag:uses ?s", subject),
            software=self._refs("?x a ag:Software ; ag:uses ?s", subject),
            mitigations=self._refs("?x a ag:Mitigation ; ag:mitigates ?s", subject),
        )

    def group(self, name: str) -> Group | None:
        needle = Literal(name.strip().casefold())
        row = self._first(
            "SELECT ?s ?id ?name ?desc WHERE { ?s a ag:Group ; ag:attackId ?id ;"
            " ag:name ?name ; ag:description ?desc ;"
            " (ag:name|ag:alias) ?label . FILTER(LCASE(STR(?label)) = ?needle) }",
            needle=needle,
        )
        if row is None:
            return None
        subject = row.s
        aliases = sorted(
            str(r.v) for r in self._query("SELECT ?v WHERE { ?s ag:alias ?v }", s=subject)
        )
        return Group(
            attack_id=str(row.id),
            name=str(row.name),
            aliases=tuple(a for a in aliases if a != str(row.name)),
            description=str(row.desc),
            techniques=self._refs("?x a ag:Technique . ?s ag:uses ?x", subject),
            software=self._refs("?x a ag:Software . ?s ag:uses ?x", subject),
        )

    def _refs(self, pattern: str, subject: URIRef) -> tuple[Ref, ...]:
        rows = self._query(
            f"SELECT ?xid ?xname WHERE {{ {pattern} . ?x ag:attackId ?xid ; ag:name ?xname }}",
            s=subject,
        )
        return tuple(sorted((Ref(str(r.xid), str(r.xname)) for r in rows),
                            key=lambda ref: ref.attack_id))

    def _query(self, sparql: str, **bindings):
        # Bound values go through initBindings, never string formatting,
        # so user input cannot change the query's shape.
        return self._graph.query(sparql, initNs={"ag": AG}, initBindings=bindings)

    def _first(self, sparql: str, **bindings):
        return next(iter(self._query(sparql, **bindings)), None)


def _add_object(graph: Graph, obj: dict) -> bool:
    kind = _STIX_KINDS.get(obj.get("type"))
    if kind is None or obj.get("revoked") or obj.get("x_mitre_deprecated"):
        return False
    attack_id = next(
        (ref["external_id"] for ref in obj.get("external_references", [])
         if ref.get("source_name") == "mitre-attack"),
        None,
    )
    if attack_id is None:
        return False

    subject = URIRef(f"urn:stix:{obj['id']}")
    graph.add((subject, RDF.type, kind))
    graph.add((subject, AG.attackId, Literal(attack_id)))
    graph.add((subject, AG.name, Literal(obj["name"])))
    graph.add((subject, AG.description, Literal(obj.get("description", ""))))
    for alias in obj.get("aliases", []):
        graph.add((subject, AG.alias, Literal(alias)))
    for phase in obj.get("kill_chain_phases", []):
        graph.add((subject, AG.tactic, Literal(phase["phase_name"])))
    return True


def _add_relationship(graph: Graph, obj: dict, known: set[str]) -> None:
    predicate = _RELATIONS.get(obj.get("relationship_type"))
    if obj.get("type") != "relationship" or predicate is None:
        return
    source, target = obj["source_ref"], obj["target_ref"]
    if source in known and target in known:
        graph.add((URIRef(f"urn:stix:{source}"), predicate, URIRef(f"urn:stix:{target}")))
