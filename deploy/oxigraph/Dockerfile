# The official Oxigraph image has no shell and runs as root, so it cannot host a
# health check or a non-root user. Reuse its binary on a normal slim base instead.
FROM ghcr.io/oxigraph/oxigraph:0.5.13@sha256:260454ee29c091d2cdb99dd156212594ff3127850627adb4cfdcd9b1e425d480 AS oxigraph

FROM python:3.12-slim-bookworm@sha256:44cf1793efa7c7a476bb0f2cff81443f4a072c90c1cb127e2924933daa3e8c64
# The database library inside the binary needs the C++ runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && install -d -o app -g app /data
COPY --from=oxigraph /usr/local/bin/oxigraph /usr/local/bin/oxigraph
USER 10001
EXPOSE 7878
# An empty ASK query: succeeds only when the server is up and can run SPARQL.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:7878/query', b'ASK{}', {'Content-Type': 'application/sparql-query'}), timeout=2)"]
CMD ["oxigraph", "serve", "--location", "/data", "--bind", "0.0.0.0:7878"]
