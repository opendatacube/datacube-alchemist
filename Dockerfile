ARG py_env_path=/env
ARG V_BASE=3.3.0

FROM opendatacube/geobase-builder:${V_BASE} as env_builder
ENV LC_ALL=C.UTF-8
ARG py_env_path

COPY requirements.txt constraints.txt /tmp/
RUN env-build-tool new /tmp/requirements.txt /tmp/constraints.txt ${py_env_path}

# Copy source code and install it
RUN mkdir -p /code
WORKDIR /code
ADD . /code

ENV PATH="${py_env_path}/bin:${PATH}"
RUN pip install --extra-index-url="https://packages.dea.ga.gov.au" -c /tmp/constraints.txt .

# Make sure it's working first
RUN datacube-alchemist --version

# Build the production runner stage from here
FROM opendatacube/geobase-runner:${V_BASE}
ARG py_env_path=/env

# Environment can be whatever is supported by setup.py
# so, either deployment, test
ARG ENVIRONMENT=deployment
RUN echo "Environment is: $ENVIRONMENT"

ENV LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    SHELL=bash

RUN apt-get update \
    && apt-get install -y \
    git vim nano fish wget postgresql libgfortran5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=env_builder $py_env_path $py_env_path
ENV PATH="${py_env_path}/bin:${PATH}"

# Set up a nice workdir, and only copy the things we care about in
ENV APPDIR=/code
RUN mkdir -p $APPDIR
WORKDIR $APPDIR
ADD . $APPDIR

RUN datacube-alchemist --version

# These ENVIRONMENT flags make this a bit complex, but basically, if we are in dev
# then we want to link the source (with the -e flag) and if we're in prod, we
# want to delete the stuff in the /code folder to keep it simple.

RUN if [ "$ENVIRONMENT" = "deployment" ] ; then\
        rm -rf $APPDIR ;\
        #Open Dask Dashboard port in dev
        EXPOSE 8787;\
    else \
        pip install --extra-index-url="https://packages.dea.ga.gov.au" \
        -c /code/constraints.txt --editable .[$ENVIRONMENT] ; \
    fi

RUN datacube-alchemist --version

CMD ["datacube-alchemist", "--help"]
