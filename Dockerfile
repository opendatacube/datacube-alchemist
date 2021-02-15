FROM opendatacube/geobase:wheels as env_builder
ARG py_env_path=/env

COPY requirements.txt /tmp
RUN env-build-tool new /tmp/requirements.txt ${py_env_path}

ENV PATH=${py_env_path}/bin:$PATH

# Copy source code and install it
RUN mkdir -p /code
WORKDIR /code
ADD . /code

RUN pip install --use-feature=2020-resolver --extra-index-url="https://packages.dea.ga.gov.au" .

# Make sure it's working first
RUN datacube-alchemist --version

# Build the production runner stage from here
FROM opendatacube/geobase:runner

ENV LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    SHELL=bash

RUN apt-get update \
    && apt-get install -y \
    git vim nano fish wget postgresql \
    && rm -rf /var/lib/apt/lists/*

COPY --from=env_builder /env /env
ENV PATH=/env/bin:$PATH

# Environment can be whatever is supported by setup.py
# so, either deployment, test
ARG ENVIRONMENT=deployment
RUN echo "Environment is: $ENVIRONMENT"

# Set up a nice workdir, and only copy the things we care about in
ENV APPDIR=/code
RUN mkdir -p $APPDIR
WORKDIR $APPDIR
ADD . $APPDIR

# These ENVIRONMENT flags make this a bit complex, but basically, if we are in dev
# then we want to link the source (with the -e flag) and if we're in prod, we
# want to delete the stuff in the /code folder to keep it simple.
RUN if [ "$ENVIRONMENT" = "deployment" ] ; then rm -rf $APPDIR ; \
    else pip install --extra-index-url="https://packages.dea.ga.gov.au" --editable .[$ENVIRONMENT] ; \
    fi

RUN datacube-alchemist --version

CMD ["datacube-alchemist", "--help"]
