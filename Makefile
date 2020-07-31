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

metadata:
	docker-compose exec jupyter \
		datacube metadata add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/restore-c3-nbart-product-name/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml

product-c3:
	docker-compose exec jupyter \
		bash -c "\
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/restore-c3-nbart-product-name/digitalearthau/config/eo3/products/nbart_ls5.odc-product.yaml;\
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/restore-c3-nbart-product-name/digitalearthau/config/eo3/products/nbart_ls7.odc-product.yaml;\
		datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/restore-c3-nbart-product-name/digitalearthau/config/eo3/products/nbart_ls8.odc-product.yaml;\
		"
index-c3:
	docker-compose exec jupyter \
		bash -c "\
			s3-find s3://dea-public-data-dev/analysis-ready-data/**/**/**/**/**/**/*.odc-metadata.yaml --no-sign-request \
			| s3-to-tar --no-sign-request | dc-index-from-tar --ignore-lineage"

run-fc-one:
	docker-comose exec datacube-alchemist run-one \


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
