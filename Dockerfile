FROM opendatacube/geobase:wheels as env_builder

COPY requirements.txt /
RUN env-build-tool new /requirements.txt /env

ENV PATH=${py_env_path}/bin:$PATH

# Copy source code and install it
RUN mkdir -p /code
WORKDIR /code
ADD . /code

RUN pip install .

# Build the production runner stage from here
FROM opendatacube/geobase:runner

ENV LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    SHELL=bash

COPY --from=env_builder /env /env
ENV PATH=${py_env_path}/bin:$PATH

# Environment can be whatever is supported by setup.py
# so, either deployment, test
ARG ENVIRONMENT=deployment
RUN echo "Environment is: $ENVIRONMENT"

# Do the apt install process, including more recent Postgres/PostGIS
RUN apt-get update && apt-get install -y wget gnupg \
    && rm -rf /var/lib/apt/lists/*
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
    apt-key add - \
    && echo "deb http://apt.postgresql.org/pub/repos/apt/ bionic-pgdg main" \
    >> /etc/apt/sources.list.d/postgresql.list

RUN apt-get update \
    && apt-get install -y \
    gfortran \
    postgresql-11 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up a nice workdir, and only copy the things we care about in
ENV APPDIR=/code
RUN mkdir -p $APPDIR
WORKDIR $APPDIR

ADD . $APPDIR

# These ENVIRONMENT flags make this a bit complex, but basically, if we are in dev
# then we want to link the source (with the -e flag) and if we're in prod, we
# want to delete the stuff in the /code folder to keep it simple.
RUN if [ "$ENVIRONMENT" = "deployment" ] ; then rm -rf $APPDIR ; \
    else /env/bin/pip install --editable .[$ENVIRONMENT] ; \
    fi

CMD ["datacube-alchemist", "--help"]
