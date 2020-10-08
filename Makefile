build:
	docker build . \
		--tag opendatacube/datacube-alchemist:test \
		--build-arg ENVIRONMENT=test

build-prod:
	docker build . \
		--tag opendatacube/datacube-alchemist:latest \
		--build-arg ENVIRONMENT=deployment

test:
	docker-compose exec alchemist pytest tests

lint:
	docker-compose exec alchemist flake8

run-prod:
	docker run --rm \
		opendatacube/datacube-alchemist

test-local:
	pytest tests


run-fc-one:
	docker-comose exec alchemist run-one \

# Docker Compose environment
build-dev:
	docker-compose build

up:
	docker-compose up

initdb:
	docker-compose exec alchemist \
		datacube system init

metadata:
	docker-compose exec alchemist \
		datacube metadata add https://raw.githubusercontent.com/opendatacube/datacube-alchemist/local-dev-env/metadata.eo_plus.yaml

product:
	docker-compose exec alchemist \
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/products/ga_s2_ard_nbar/ga_s2_ard_nbar_granule.yaml

add-one-scene:
	docker-compose exec alchemist \
		datacube dataset add s3://dea-public-data/L2/sentinel-2-nbar/S2MSIARD_NBAR/2019-09-09/S2B_OPER_MSI_ARD_TL_SGS__20190909T052856_A013099_T51LTH_N02.08/ARD-METADATA.yaml

run-one-fc:
	docker-compose exec alchemist \
		/code/datacube_alchemist/cli.py run-one \
		examples/fc_config_sentinel2b_alex.yaml bfcc7bae-f9db-4876-959a-ec495dddbb3b

run-one-wofs:
	docker-compose exec alchemist \
		/code/datacube_alchemist/cli.py run-one \
		examples/wofs_config_sentinel2b_alex.yaml bfcc7bae-f9db-4876-959a-ec495dddbb3b

shell:
	docker-compose exec alchemist bash

# C3 Related
c3-metadata:
	docker-compose exec alchemist \
		datacube metadata add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml

c3-add:
	docker-compose exec alchemist \
		datacube product add \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls5.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls7.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls8.odc-product.yaml

c3-index:
	docker-compose exec alchemist \
		bash -c "\
			s3-find s3://dea-public-data-dev/analysis-ready-data/**/*.odc-metadata.yaml --no-sign-request \
			| s3-to-tar --no-sign-request | dc-index-from-tar --ignore-lineage"

c3-populate-queue-from-ard:
	docker-compose exec alchemist \
		/code/datacube_alchemist/cli.py \
		push-to-queue-from-s3 \
		-M alchemist-nehem-backup-wofs \
		-B dea-public-data-dev \
		-P "analysis-ready-data" \
		-F "final.odc-metadata.yaml"