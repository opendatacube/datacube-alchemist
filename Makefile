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

down:
	docker-compose down

shell:
	docker-compose exec alchemist bash

test:
	docker-compose exec alchemist pytest tests

lint:
	docker-compose exec alchemist black --check datacube_alchemist

integration-test:
	docker-compose up -d
	docker-compose exec -T alchemist bash ./tests/integration_tests.sh

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
		datacube dataset add --ignore-lineage --confirm-ignore-lineage \
			s3://dea-public-data/baseline/ga_ls8c_ard_3/098/073/2020/07/19/ga_ls8c_ard_3-1-0_098073_2020-07-19_final.odc-metadata.yaml \
			s3://dea-public-data/baseline/ga_ls5t_ard_3/108/083/2010/10/02/ga_ls5t_ard_3-0-0_108083_2010-10-02_final.odc-metadata.yaml \
			s3://dea-public-data/baseline/ga_ls7e_ard_3/100/075/2003/10/15/ga_ls7e_ard_3-0-0_100075_2003-10-15_final.odc-metadata.yaml

# Landsat 8, 7 and 5 respectively
THREE_SCENES=600645a5-5256-4632-a13d-fa13d1c11a8f 8b215983-ae1b-45bd-ad63-7245248bd41b 3fda2741-e810-4d3e-a54a-279fc3cd795f

wofs-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_wo.yaml \
		--uuid 600645a5-5256-4632-a13d-fa13d1c11a8f

wofs-many:
	docker-compose exec alchemist \
		datacube-alchemist run-many --config-file ./examples/c3_config_wo.yaml --limit=2 \
		time in 2020-01

fc-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_fc.yaml \
		--uuid 600645a5-5256-4632-a13d-fa13d1c11a8f

dnbr-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_dnbr.yaml \
		--uuid 600645a5-5256-4632-a13d-fa13d1c11a8f


wofs-one-of-each:
	docker-compose exec alchemist \
		bash -c \
			"echo '${THREE_SCENES}' | xargs -n1 datacube-alchemist run-one ./examples/c3_config_wo.yaml"

fc-one-of-each:
	docker-compose exec alchemist \
		bash -c \
			"echo '${THREE_SCENES}' | xargs -n1 datacube-alchemist run-one ./examples/c3_config_fc.yaml"

find_missing:
	docker-compose exec alchemist \
		datacube-alchemist add-missing-to-queue --config-file ./examples/c3_config_wo.yaml \
			--queue alex-dev-alive \
			--dryrun


# Queue testing
wofs-to-queue:
	docker-compose exec alchemist \
		datacube-alchemist add-to-queue --config-file ./examples/c3_config_wo.yaml --queue alex-dev-alive \
			--limit=300 --product-limit=100

wofs-from-queue:
	docker-compose exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_wo.yaml --queue alex-dev-alive \
			--limit=1 --queue-timeout=600 --dryrun

fc-to-queue:
	docker-compose exec alchemist \
		datacube-alchemist add-to-queue --config-file ./examples/c3_config_fc.yaml --queue alex-dev-alive \
			--limit=20 --product-limit=5

fc-from-queue:
	docker-compose exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_fc.yaml --queue alex-dev-alive \
			--limit=1 --queue-timeout=1200

fc-deadletter:
	docker-compose exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_fc.yaml \
		--queue dea-dev-eks-alchemist-c3-processing-fc-deadletter \
		--queue-timeout=1200

wo-deadletter:
	docker-compose exec alchemist \
		datacube-alchemist run-from-queue --config-file ./examples/c3_config_wo.yaml \
		--queue dea-dev-eks-alchemist-c3-processing-wo-deadletter \
		--queue-timeout=1200

product_nci:
	docker-compose exec alchemist \
		datacube product add \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products/ard_ls5.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products/ard_ls7.odc-product.yaml \
        https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products/ard_ls8.odc-product.yaml

index_nci:
	docker-compose exec alchemist \
		bash -c "\
			find /code/examples/ga_ls8c_ard_3/ -name "*.odc-metadata.yaml" | \
			xargs datacube dataset add \
			--ignore-lineage --confirm-ignore-lineage --product=ga_ls8c_ard_3 \
		"

process_nci:
	echo "Fake"