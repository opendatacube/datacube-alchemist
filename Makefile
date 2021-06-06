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
			s3://dea-public-data/baseline/ga_ls7e_ard_3/100/075/2003/10/15/ga_ls7e_ard_3-0-0_100075_2003-10-15_final.odc-metadata.yaml \
			s3://dea-public-data/baseline/ga_ls8c_ard_3/091/089/2019/01/20/ga_ls8c_ard_3-0-0_091089_2019-01-20_final.odc-metadata.yaml

index-geomedian:
	docker-compose exec alchemist \
		bash -c "\
			datacube product add https://data.dea.ga.gov.au/geomedian-australia/v2.1.0/product-definition.yaml;\
			s3-to-dc --no-sign-request 's3://dea-public-data/geomedian-australia/v2.1.0/L8/**/*.yaml' ls8_nbart_geomedian_annual\
		"

product-s2a:
	docker-compose exec alchemist \
		datacube product add \
		https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/s2_ard_granule.odc-product.yaml

index-s2a:
	docker-compose exec alchemist \
		bash -c "\
			s3-to-dc --no-sign-request 's3://dea-public-data/baseline/s2a_ard_granule/**/*.yaml' s2a_ard_granule\
		"

metadata-s2-nrt:
	docker-compose exec alchemist \
		datacube metadata add \
			https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/products/nrt/sentinel/eo_s2_nrt.odc-type.yaml

product-s2-nrt:
	docker-compose exec alchemist \
		datacube product add \
			https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/products/nrt/sentinel/s2_nrt.products.yaml

metadata-eo_plus:
	docker-compose exec alchemist \
		datacube metadata add \
			https://raw.githubusercontent.com/opendatacube/datacube-dataset-config/master/metadata_types/eo_plus.odc-type.yaml

index-s2-nrt:
	docker-compose exec alchemist \
		datacube dataset add --ignore-lineage --confirm-ignore-lineage \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-12/S2B_OPER_MSI_ARD_TL_VGS4_20210512T014256_A021835_T56JKM_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-05/S2B_OPER_MSI_ARD_TL_VGS4_20210506T011341_A021749_T56GMA_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-05/S2A_OPER_MSI_ARD_TL_VGS4_20210505T024121_A030644_T53LRJ_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-18/S2A_OPER_MSI_ARD_TL_VGS4_20210518T025201_A030830_T53KLV_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-16/S2A_OPER_MSI_ARD_TL_VGS1_20210516T054329_A030802_T50JMS_N03.00/ARD-METADATA.yaml

quickstart: initdb metadata product index index-geomedian metadata-s2-nrt product-s2-nrt metadata-eo_plus index-s2-nrt product-s2a index-s2a


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

# f9a66dde-d423-47b5-8421-a71cfb1d8883 = https://data.dea.ga.gov.au/?prefix=L2/sentinel-2-nrt/S2MSIARD/2021-05-16/S2A_OPER_MSI_ARD_TL_VGS1_20210516T054329_A030802_T50JMS_N03.00/

dnbr-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_dnbr_3band.yaml \
		--uuid f9a66dde-d423-47b5-8421-a71cfb1d8883

bai-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_bai.yaml \
		--uuid c37f3228-f350-4f50-8165-86232051319b

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
