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
RUN pip3 install numexpr s3fs
RUN apt-get install -y emacs

ENV FILE_PREFIX="" \
    DATACUBE_CONFIG_PATH="/opt/custom-config.conf" \
    DB_HOSTNAME="localhost" \
    DB_PORT="5432" \
    DB_USERNAME="africa" \
    DB_PASSWORD="" \
    DB_DATABASE="africa" \
    SQS_QUEUE="alchemist-standard" \
    SQS_TIMEOUT_SEC="500" \
    COMMAND="" \
    EXPRESSIONS=""


# Set up an entrypoint that drops environment variables into the config file
ENTRYPOINT ["docker-entrypoint.sh"]

#CMD ["python3", "datacube_alchemist/cloud_wrapper.py"]
CMD ["datacube-alchemist", "--help"]
#CMD ["sh", "-c", "datacube-alchemist pull_from_queue $SQS_QUEUE -s $SQS_TIMEOUT_SEC"]