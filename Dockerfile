FROM ghcr.io/osgeo/gdal:ubuntu-small-3.8.5 AS base

FROM base

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PATH=/root/.local/bin:$PATH

# Apt installation
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
      build-essential \
      fish \
      git \
      vim \
      nano \
      wget \
      python3-pip \
      # For FC
      libgfortran5 \
      # For Shapely & friends.
      libgeos-dev \
      libhdf5-dev \
      libnetcdf-dev \
      libudunits2-dev \
      libproj-dev \
      # For Psycopg2
      libpq-dev \
      python3-dev \
    # Fiona 1.10 does not install with older setuptools. Use user-installed
    # pip and wheel as well to avoid confusing the package system.
    && pip install -I --user pip wheel 'setuptools>=69.0' \
    && apt-get purge -y python3-setuptools python3-pip python3-wheel \
    && apt-get autoclean && \
    apt-get autoremove && \
    rm -rf /var/lib/{apt,dpkg,cache,log}

# Environment can be whatever is supported by setup.py
# so, either deployment, test
ARG ENVIRONMENT=deployment
ENV APPDIR=/code
RUN echo "Environment is: $ENVIRONMENT" && \
  mkdir -p /conf $APPDIR
COPY requirements.txt /conf/
RUN pip install --root-user-action ignore -r /conf/requirements.txt

WORKDIR $APPDIR
COPY . $APPDIR

# These ENVIRONMENT flags make this a bit complex, but basically, if we are in dev
# then we want to link the source (with the -e flag) and if we're in prod, we
# want to delete the stuff in the /code folder to keep it simple.
RUN if [ "$ENVIRONMENT" = "deployment" ] ; then\
        pip install . ; \
        rm -rf $APPDIR/* ; \
    else \
        pip install --editable ".[$ENVIRONMENT]" ; \
    fi && \
    pip freeze && \
    datacube-alchemist --version

CMD ["datacube-alchemist", "--help"]
