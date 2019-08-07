FROM opendatacube/datacube-core:1.7

RUN pip install -r requirements.txt &&
    pip install .