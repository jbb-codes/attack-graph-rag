"""Keep the ATT&CK graph in a separate SPARQL server instead of in memory.

Used by Docker Compose, where the graph lives in its own container and
survives restarts. The server must offer two HTTP endpoints under one base
address (Oxigraph does): POST <base>/query to run SPARQL, and
PUT <base>/store?default to replace the whole default graph.
"""

import urllib.error
import urllib.request

from rdflib import Graph
from rdflib.plugins.stores.sparqlstore import SPARQLStore

from attack_graph.graph import AttackGraph

_TIMEOUT_SECONDS = 30
_UPLOAD_TIMEOUT_SECONDS = 300  # the full ATT&CK graph is tens of MB


class GraphServerError(Exception):
    """The SPARQL server could not be reached or refused a request. Never carries the address."""


class SparqlServer:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def graph(self) -> AttackGraph:
        """A graph whose queries run on the server. Fails now, not on first lookup, if it is down."""
        store = SPARQLStore(
            query_endpoint=f"{self._base}/query",
            returnFormat="json",
            method="POST_FORM",
            timeout=_TIMEOUT_SECONDS,
        )
        graph = Graph(store=store)
        graph.bind("ag", AttackGraph.NAMESPACE)
        try:
            graph.query("ASK {}")
        except Exception as exc:  # urllib, HTTP and parse errors all mean "unusable"
            raise GraphServerError(f"Cannot query the SPARQL server ({type(exc).__name__}).") from exc
        return AttackGraph(graph)

    def replace(self, ntriples: bytes) -> None:
        """Make the server's graph exactly these facts, so reloading never duplicates anything."""
        request = urllib.request.Request(
            f"{self._base}/store?default",
            data=ntriples,
            method="PUT",
            headers={"Content-Type": "application/n-triples"},
        )
        try:
            # URL is checked to be http(s) in config.py, so file: and custom schemes cannot reach here.
            with urllib.request.urlopen(request, timeout=_UPLOAD_TIMEOUT_SECONDS):  # nosec B310
                pass
        except (urllib.error.URLError, OSError) as exc:
            raise GraphServerError(f"The SPARQL server did not accept the graph ({type(exc).__name__}).") from exc
