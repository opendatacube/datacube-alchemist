FROM opendatacube/datacube-core:1.7

ENV APPDIR=/tmp/code/
RUN mkdir -p $APPDIR
COPY requirements* $APPDIR/
WORKDIR $APPDIR


RUN pip3 install --upgrade pip \
    && pip3 install -r requirements-docker.txt \
    && rm -rf $HOME/.cache/pip


COPY . $APPDIR
RUN pip3 install . \
    && rm -rf $HOME/.cache/pip

# Set up an entrypoint that drops environment variables into the config file
ENTRYPOINT ["docker-entrypoint.sh"]

CMD ["datacube-alchemist", "--help"]