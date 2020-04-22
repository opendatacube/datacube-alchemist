build:
	docker build . \
		--tag opendatacube/datacube-alchemist:test \
		--build-arg ENVIRONMENT=test

build-prod:
	docker build . \
		--tag opendatacube/datacube-alchemist:latest \
		--build-arg ENVIRONMENT=production

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
	docker-compose run alchemist \
		datacube system init

metadata:
	docker-compose run alchemist \
		datacube metadata add https://raw.githubusercontent.com/opendatacube/datacube-alchemist/local-dev-env/metadata.eo_plus.yaml

product-sentinel2:
	docker-compose run alchemist \
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/dev/products/ga_s2_ard_nbar/ga_s2_ard_nbar_granule.yaml

add-happy-scene:
	docker-compose run alchemist \
		datacube dataset add s3://dea-public-data/L2/sentinel-2-nbar/S2MSIARD_NBAR/2019-09-09/S2B_OPER_MSI_ARD_TL_SGS__20190909T052856_A013099_T51LTH_N02.08/ARD-METADATA.yaml

add-failed-scene:
	docker-compose run alchemist \
		datacube dataset add s3://dea-public-data/L2/sentinel-2-nbar/S2MSIARD_NBAR/2019-01-08/S2B_OPER_MSI_ARD_TL_SGS__20190108T021617_A009609_T53HNE_N02.07/ARD-METADATA.yaml

run-happy-one:
	docker-compose run alchemist \
		/code/datacube_alchemist/cli.py run-one \
		examples/fc_config_sentinel2b_test.yaml bfcc7bae-f9db-4876-959a-ec495dddbb3b

run-one:
	docker-compose run alchemist \
		./datacube_alchemist/cli.py run_one \
		examples/fc_config_sentinel2b_test.yaml 95f69a40-ba51-43fd-b309-2a2a346bb485

shell:
	docker-compose run alchemist bash
