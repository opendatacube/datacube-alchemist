FROM opendatacube/datacube-core:1.7

ENV APPDIR=/tmp/code
RUN mkdir -p $APPDIR
COPY . $APPDIR
WORKDIR $APPDIR


RUN pip3 install --upgrade pip \
    && pip3 install -r requirements.txt \
    && pip3 install . \
    && rm -rf $HOME/.cache/pip

RUN apt-get update && apt-get install -y gfortran  \
    && rm -rf  /var/lib/apt/lists/*
RUN pip3 install git+https://github.com/GeoscienceAustralia/fc --no-deps --global-option=build --global-option='--executable=/usr/bin/env python3'  \
    && rm -rf $HOME/.cache/pip
RUN pip3 install git+https://github.com/GeoscienceAustralia/wofs --no-deps --global-option=build --global-option='--executable=/usr/bin/env python3'  \
    && rm -rf $HOME/.cache/pip
RUN pip3 install numexpr s3fs  \
    && rm -rf $HOME/.cache/pip

# Set up an entrypoint that drops environment variables into the config file
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["datacube-alchemist", "--help"]