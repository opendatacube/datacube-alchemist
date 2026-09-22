FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv

FROM ghcr.io/osgeo/gdal:ubuntu-full-3.13.3@sha256:2dd0f81ef927ff4c3d4dbe4f73c029dc86d4073974c0564f8e196f6e1412e2e0 AS base

ENV LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Both the builder image and the regular image needs build tools, otherwise "uv sync"
# will fail.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libgdal-dev \
        # For shapely with --no-binary.
        libgeos-dev \
        libhdf5-dev \
        libnetcdf-dev \
        libudunits2-dev \
        libproj-dev \
        # For psycopg2.
        libpq-dev \
        # For FC
        libgfortran5 \
        python3-dev

FROM base AS builder

RUN which x86_64-linux-gnu-gcc

ENV UV_COMPILE_BYTECODE=0 \
    UV_HTTP_RETRIES=10 \
    UV_PROJECT_ENVIRONMENT=/app \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.14

WORKDIR /build

COPY --link --from=uv /uv /uvx /usr/local/bin/

COPY --link pyproject.toml uv.lock /build/

# Use a separate cache volume for uv on opendatacube projects, so it is
# not inseparable from pip/poetry/npm/etc. cache stored in /root/.cache.
# Note that fiona bundles libgdal and SHOULD be compiled locally, but the
# latest release at time of writing (1.10.1) does not compile cleanly against
# Python 3.14.
RUN --mount=type=cache,id=opendatacube-uv-cache,target=/root/.cache \
    uv sync --locked --all-extras --no-install-project \
      --no-binary-package fiona \
      --no-binary-package rasterio \
      --no-binary-package shapely

FROM base

COPY --from=builder --link /usr/local/bin/uv* /usr/local/bin/

ARG V_PG=18

# Update and install Ubuntu packages
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    export DEBIAN_FRONTEND=noninteractive \
    && apt-get -qq update \
    && apt-get upgrade -y \
    && apt-get -qq -y --no-install-recommends install dirmngr gpg-agent  > /dev/null \
    && export GNUPGHOME="$(mktemp -d)" \
    && pg_key="B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8" \
    && gpg --batch --keyserver keyserver.ubuntu.com --recv-keys "$pg_key" \
    && gpg --batch --export --armor "$pg_key" > /etc/apt/keyrings/postgres.gpg.asc \
    && gpgconf --kill all \
    && echo "deb [signed-by=/etc/apt/keyrings/postgres.gpg.asc] http://apt.postgresql.org/pub/repos/apt resolute-pgdg main $V_PG" | tee /etc/apt/sources.list.d/postgres.list \
    && apt-get -qq update \
    && apt-get install -y --no-install-recommends \
        gosu \
        less \
        postgresql-client-${V_PG} \
        sudo \
        nano \
        vim \
        tini


# users and groups.
RUN usermod -aG sudo ubuntu \
  && echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \
  && mkdir /app /code \
  && chown ubuntu:ubuntu /app /code

# Build constrained python environment

USER ubuntu

ENV PATH=/app/bin:$PATH

COPY --from=builder --link --chown=1000:1000 /app /app

# Copy datacube-core source code into container and install from source (with addons for tests).
COPY --chown=1000:1000 --link . /code

WORKDIR /code

USER root

# Install as root to have the right permissions in cache, but chown result to ubuntu.
RUN  --mount=type=cache,id=opendatacube-uv-cache,target=/root/.cache \
    . /app/bin/activate \
    && export UV_COMPILE_BYTECODE=0 \
    && export UV_PROJECT_ENVIRONMENT=/app \
    && export UV_PYTHON_DOWNLOADS=never \
    && export UV_PYTHON=python3.14 \
    && uv pip install /code[ops]

CMD ["datacube-alchemist", "--help"]
