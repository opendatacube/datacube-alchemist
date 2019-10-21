FROM opendatacube/datacube-core:1.7

ENV APPDIR=/tmp/code/
RUN mkdir -p $APPDIR
COPY requirements* $APPDIR/
WORKDIR $APPDIR

RUN apt-get update && apt-get install -y gfortran \
&& rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip \
    && pip3 install -r requirements-docker.txt \
    && pip3 install scipy ephem \
    && rm -rf $HOME/.cache/pip


COPY . $APPDIR
RUN pip3 install . \
    && rm -rf $HOME/.cache/pip

RUN pip3 install git+https://github.com/GeoscienceAustralia/wofs --no-deps --global-option=build --global-option='--executable=/usr/bin/env python3'

# Set up an entrypoint that drops environment variables into the config file
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["datacube-alchemist", "--help"]