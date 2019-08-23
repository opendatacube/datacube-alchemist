FROM opendatacube/datacube-core:1.7

ENV APPDIR=/tmp/code
RUN mkdir -p $APPDIR
COPY . $APPDIR
WORKDIR $APPDIR


RUN pip3 install --upgrade pip \
    && pip3 install -r requirements.txt \
    && pip3 install . \
    && rm -rf $HOME/.cache/pip

RUN apt-get update && apt-get install -y gfortran
RUN pip3 install git+https://github.com/GeoscienceAustralia/fc --no-deps --global-option=build --global-option='--executable=/usr/bin/env python3'
RUN pip3 install numexpr

ENV FILE_PREFIX="" \
    DB_HOSTNAME="localhost" \
    DB_PORT="5432" \
    DB_USERNAME="africa" \
    DB_PASSWORD="" \
    SQS_QUEUE="alchemist-standard" \
   $SQS_TIMEOUT_SEC=500 \
    MAKE_PUBLIC="True"

CMD ["sh", "-c", "datacube-alchemist pull_from_queue $SQS_QUEUE -s $SQS_TIMEOUT_SEC", ]