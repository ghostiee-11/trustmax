# Trustmax backend (FastAPI) for cloud deploy.
# Builds a self-contained image: installs slim deps, seeds a small demo corpus + embedded knowledge
# graph at build time, then serves the API. No external Neo4j or paid services required.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GRAPH_BACKEND=networkx \
    EMBED_BACKEND=hash \
    DATA_SCALE=cloud

WORKDIR /app

COPY requirements-deploy.txt ./
RUN pip install -r requirements-deploy.txt

COPY app ./app

# Bake the demo data + knowledge graph into the image (uses the offline mock model, no key needed).
RUN python -m app.deploy_seed

EXPOSE 8000
# Render provides $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
