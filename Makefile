build-image:
	docker build . \
		--tag opendatacube/datacube-alchemist:test \
		--build-arg ENVIRONMENT=test

build-prod-image:
	docker build . \
		--tag opendatacube/datacube-alchemist:latest \
		--build-arg ENVIRONMENT=deployment

run-prod:
	docker run --rm \
		opendatacube/datacube-alchemist

test-local:
	pytest tests


# Docker Compose environment
build:
	docker-compose build

up:
	docker-compose up

shell:
	docker-compose exec alchemist bash

test:
	docker-compose exec alchemist pytest tests

lint:
	docker-compose exec alchemist flake8


# C3 Related
initdb:
	docker-compose exec alchemist \
		datacube system init

metadata:
	docker-compose exec alchemist \
		datacube metadata add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml

product:
	docker-compose exec alchemist \
		datacube product add \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls5.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls7.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls8.odc-product.yaml

index:
	docker-compose exec alchemist \
		bash -c "s3-to-dc 's3://dea-public-data-dev/analysis-ready-data/**/*.odc-metadata.yaml'\
			--no-sign-request --skip-lineage 'ga_ls8c_ard_3 ga_ls7e_ard_3 ga_ls5t_ard_3'"

# LS8 example: 7b9553d4-3367-43fe-8e6f-b45999c5ada6
# LS7 example: b03ab26f-dcb3-408f-9f78-f4bf4b84cb4b
# LS5 example: 76223191-e942-4e26-b116-8c072e87d843

wofs-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one ./examples/c3_config_wo.yaml 7b9553d4-3367-43fe-8e6f-b45999c5ada6


fc-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one ./examples/c3_config_fc.yaml 7b9553d4-3367-43fe-8e6f-b45999c5ada6

wofs-one-of-each:
	echo "go"

fc-one-of-each:
	echo "go"

c3-populate-queue-from-ard:
	docker-compose exec alchemist \
		/code/datacube_alchemist/cli.py \
		push-to-queue-from-s3 \
		-M alchemist-nehem-backup-wofs \
		-B dea-public-data-dev \
		-P "analysis-ready-data" \
		-F "final.odc-metadata.yaml"
