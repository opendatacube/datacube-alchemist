FROM opendatacube/datacube-core:1.7

ENV APPDIR=/tmp/code
RUN mkdir -p $APPDIR
COPY . $APPDIR
WORKDIR $APPDIR


RUN pip3 install --upgrade pip \
    && pip3 install -r requirements.txt \
    && pip3 install . \
    && rm -rf $HOME/.cache/pip

CMD ["datacube-alchemist", "--help"]