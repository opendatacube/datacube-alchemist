build:
	docker build . \
		--tag opendatacube/datacube-alchemist:test \
		--build-arg ENVIRONMENT=test

build-prod:
	docker build . \
		--tag opendatacube/datacube-alchemist:latest \
		--build-arg ENVIRONMENT=deployment

test:
	docker run --rm \
		opendatacube/datacube-alchemist:test \
			pytest tests

lint:
	docker run --rm \
		opendatacube/datacube-alchemist:test \
			flake8

run-prod:
	docker run --rm \
		opendatacube/datacube-alchemist

test-local:
	pytest tests

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
