FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pipeline ./pipeline
COPY dbt ./dbt
COPY tests ./tests
COPY ml ./ml
COPY api ./api

ENV DBT_PROFILES_DIR=/app/dbt

ENTRYPOINT ["python", "-m", "pipeline.cli"]
