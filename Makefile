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

down:
	docker-compose down

initdb:
	docker-compose exec alchemist \
		datacube system init

metadata:
	docker-compose exec alchemist \
		datacube metadata add https://raw.githubusercontent.com/opendatacube/datacube-alchemist/local-dev-env/metadata.eo_plus.yaml

africa-product:
	docker-compose exec alchemist \
		datacube product add https://raw.githubusercontent.com/digitalearthafrica/config/master/products/esa_s2_l2a.yaml

product:
	docker-compose exec alchemist \
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/products/ga_s2_ard_nbar/ga_s2_ard_nbar_granule.yaml

add-africa-scene:
	docker-compose exec alchemist \
		s3-to-dc --stac s3://sentinel-cogs/sentinel-s2-l2a-cogs/2020/S2A_28PBR_20200429_0_L2A/**/*.json s2_l2a

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
		examples/wofs_config_sentinel2b_alex.yaml ebcad5d5-e53e-5f80-8cea-550b8624f714

shell:
	docker-compose exec alchemist bash
