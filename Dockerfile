FROM osgeo/gdal:ubuntu-small-3.4.1

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# Apt installation
RUN apt-get update && \
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
      # For Psycopg2
      libpq-dev python-dev \
    && apt-get autoclean && \
    apt-get autoremove && \
    rm -rf /var/lib/{apt,dpkg,cache,log}

# Environment can be whatever is supported by setup.py
# so, either deployment, test
ARG ENVIRONMENT=deployment
RUN echo "Environment is: $ENVIRONMENT"

# Pip installation
RUN mkdir -p /conf
COPY requirements.txt /conf/
RUN pip install -r /conf/requirements.txt

# Set up a nice workdir and add the live code
ENV APPDIR=/code
RUN mkdir -p $APPDIR
WORKDIR $APPDIR
ADD . $APPDIR

# These ENVIRONMENT flags make this a bit complex, but basically, if we are in dev
# then we want to link the source (with the -e flag) and if we're in prod, we
# want to delete the stuff in the /code folder to keep it simple.
# no-use-pep517 because of this https://github.com/pypa/pip/issues/7953
RUN if [ "$ENVIRONMENT" = "deployment" ] ; then\
        pip install . ; \
        rm -rf $APPDIR/* ; \
    else \
        pip install --no-use-pep517 --editable ".[$ENVIRONMENT]" ; \
    fi

RUN pip freeze

# Check it works
RUN datacube-alchemist --version

CMD ["datacube-alchemist", "--help"]
