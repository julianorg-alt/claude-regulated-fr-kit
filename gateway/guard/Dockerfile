# syntax=docker/dockerfile:1
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
# Dependencies pinned by version and hash (requirements.txt is exported from uv.lock).
# Build context: the repository root (gateway/compose.yaml), filtered by .dockerignore.
COPY gateway/guard/requirements.txt /app/requirements.txt
# Optional build secret "build_ca": CA bundle of a TLS-inspecting proxy, for builds behind one.
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir --require-hashes --only-binary=:all: -r /app/requirements.txt \
    && useradd --uid 10001 --create-home app && mkdir /data && chown app /data
COPY gateway/guard/crfr_guard /app/crfr_guard
COPY pseudonymisation/crfr_pseudo /app/crfr_pseudo
WORKDIR /app
USER 10001
EXPOSE 9002
HEALTHCHECK --interval=5s --timeout=2s --start-period=60s CMD python -c "import socket;socket.create_connection(('127.0.0.1',9002),1)"
CMD ["python", "-s", "-E", "-m", "crfr_guard.server"]
