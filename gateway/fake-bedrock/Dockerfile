FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
RUN useradd --uid 10001 --create-home app && mkdir /data && chown app /data
COPY fake_bedrock.py /app/fake_bedrock.py
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=2s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["python", "-I", "/app/fake_bedrock.py"]
