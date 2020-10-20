
DOCKER_COMMAND=docker-compose -f docker-compose.yml -f docker-compose-dev.yml

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
	${DOCKER_COMMAND} build

up:
	${DOCKER_COMMAND} up

down:
	${DOCKER_COMMAND} down

shell:
	${DOCKER_COMMAND} exec alchemist bash

test:
	${DOCKER_COMMAND} exec alchemist pytest tests

lint:
	${DOCKER_COMMAND} exec alchemist flake8

integration-test:
	# Careful, this will drop your postgres
	docker-compose build
	docker-compose up -d
	docker-compose exec -T alchemist bash ./tests/integration_tests.sh
	docker-compose down

# C3 Related
initdb:
	${DOCKER_COMMAND} exec alchemist \
		datacube system init

metadata:
	${DOCKER_COMMAND} exec alchemist \
		datacube metadata add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml

product:
	${DOCKER_COMMAND} exec alchemist \
		datacube product add \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls5.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls7.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls8.odc-product.yaml

index:
	${DOCKER_COMMAND} exec alchemist \
		bash -c "s3-to-dc 's3://dea-public-data-dev/analysis-ready-data/**/*.odc-metadata.yaml'\
			--no-sign-request --skip-lineage 'ga_ls8c_ard_3 ga_ls7e_ard_3 ga_ls5t_ard_3'"

# LS8 example: 7b9553d4-3367-43fe-8e6f-b45999c5ada6
# LS7 example: b03ab26f-dcb3-408f-9f78-f4bf4b84cb4b
# LS5 example: 76223191-e942-4e26-b116-8c072e87d843

THREE_SCENES=7b9553d4-3367-43fe-8e6f-b45999c5ada6 b03ab26f-dcb3-408f-9f78-f4bf4b84cb4b 76223191-e942-4e26-b116-8c072e87d843

wofs-one:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_wo.yaml \
		--uuid 7b9553d4-3367-43fe-8e6f-b45999c5ada6

wofs-many:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist run-many --config-file ./examples/c3_config_wo.yaml --limit=2 \
		time in 2020-01

fc-one:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_fc.yaml \
		--uuid 7b9553d4-3367-43fe-8e6f-b45999c5ada6

wofs-one-of-each:
	${DOCKER_COMMAND} exec alchemist \
		bash -c \
			"echo '${THREE_SCENES}' | xargs -n1 datacube-alchemist run-one ./examples/c3_config_wo.yaml"

fc-one-of-each:
	${DOCKER_COMMAND} exec alchemist \
		bash -c \
			"echo '${THREE_SCENES}' | xargs -n1 datacube-alchemist run-one ./examples/c3_config_fc.yaml"

c3-populate-queue-from-ard:
	${DOCKER_COMMAND} exec alchemist \
		/code/datacube_alchemist/cli.py \
		push-to-queue-from-s3 \
		-M alchemist-nehem-backup-wofs \
		-B dea-public-data-dev \
		-P "analysis-ready-data" \
		-F "final.odc-metadata.yaml"

# Queue testing
wofs-to-queue:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist add-to-queue --config-file ./examples/c3_config_wo.yaml --queue alex-dev-alive \
			--limit=20 --product-limit=5

wofs-from-queue:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_wo.yaml --queue alex-dev-alive \
			--limit=1 --queue-timeout=600

fc-to-queue:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist add-to-queue --config-file ./examples/c3_config_fc.yaml --queue alex-dev-alive \
			--limit=20 --product-limit=5

fc-from-queue:
	${DOCKER_COMMAND} exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_fc.yaml --queue alex-dev-alive \
			--limit=1 --queue-timeout=600
