# Postgres 16 with BOTH PostGIS and pgvector — no official image ships the two together.
# (Managed Postgres like RDS/Neon has both available; this image is for dev + self-hosted prod.)
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
