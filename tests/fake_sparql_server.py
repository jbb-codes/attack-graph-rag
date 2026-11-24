"""A tiny in-process SPARQL server over loopback, so tests can exercise the HTTP path offline.

It speaks the same two endpoints as the real server (Oxigraph): POST /query
to run SPARQL, and PUT /store?default to replace the whole graph.
"""

import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from rdflib import Graph


class FakeSparqlServer:
    def __init__(self) -> None:
        self.graph = Graph()
        self.fail_with: int | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # keep test output quiet
                pass

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))

            def _reply(self, status: int, body: bytes = b"", kind: str = "text/plain") -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _query(self, sparql: str) -> None:
                result = outer.graph.query(sparql)
                self._reply(200, result.serialize(format="json"), "application/sparql-results+json")

            def do_POST(self) -> None:
                if outer.fail_with:
                    return self._reply(outer.fail_with)
                body = self._body()
                if self.headers.get("Content-Type", "").startswith("application/sparql-query"):
                    return self._query(body.decode())
                self._query(parse_qs(body.decode())["query"][0])

            def do_GET(self) -> None:
                if outer.fail_with:
                    return self._reply(outer.fail_with)
                self._query(parse_qs(urlparse(self.path).query)["query"][0])

            def do_PUT(self) -> None:
                if outer.fail_with:
                    return self._reply(outer.fail_with)
                graph = Graph()
                graph.parse(data=self._body().decode(), format="nt")
                outer.graph = graph
                self._reply(204)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def sparql_server():
    server = FakeSparqlServer()
    try:
        yield server
    finally:
        server.close()
