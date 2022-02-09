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

pip-compile:
	pip-compile --upgrade --output-file requirements.txt requirements.in


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

# Landsat geomedian
index-geomedian:
	docker-compose exec alchemist \
		bash -c "\
			datacube product add https://data.dea.ga.gov.au/geomedian-australia/v2.1.0/product-definition.yaml;\
			s3-to-dc --no-sign-request 's3://dea-public-data/geomedian-australia/v2.1.0/L8/**/*.yaml' ls8_nbart_geomedian_annual\
		"

# s2a required for on-the-fly gm calculation
product-s2a:
	docker-compose exec alchemist \
		datacube product add \
		https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/s2_ard_granule.odc-product.yaml

index-s2a:
	docker-compose exec alchemist \
		bash -c "\
			s3-to-dc --no-sign-request 's3://dea-public-data/baseline/s2a_ard_granule/**/*.yaml' s2a_ard_granule\
		"

# Barest Earth required for NRT calculation
product-s2be:
	docker-compose exec alchemist \
		datacube product add \
		https://explorer.dev.dea.ga.gov.au/products/s2_barest_earth.odc-product.yaml

index-s2be:
	docker-compose exec alchemist \
		bash -c "\
			s3-to-dc --no-sign-request 's3://dea-public-data-dev/s2be/*/*odc-metadata.yaml' s2_barest_earth\
		"

# Add s2 c3 datasets
product-s2-c3:
	docker-compose exec alchemist \
		datacube product add \
		https://explorer.dev.dea.ga.gov.au/products/ga_s2am_ard_provisional_3.odc-product.yaml
	docker-compose exec alchemist \
		datacube product add \
		https://explorer.dev.dea.ga.gov.au/products/ga_s2bm_ard_provisional_3.odc-product.yaml

index-s2-c3:
	docker-compose exec alchemist \
		datacube dataset add --ignore-lineage --confirm-ignore-lineage \
			s3://dea-public-data/baseline/ga_s2am_ard_provisional_3/51/KWV/2021/08/18_nrt/20210818T033715/ga_s2am_ard_provisional_3-2-1_51KWV_2021-08-18_nrt.odc-metadata.yaml \

# Specific BE dataset for local testing
index-one-s2be:
	docker-compose exec alchemist \
		datacube dataset add --ignore-lineage --confirm-ignore-lineage \
			https://dea-public-data-dev.s3.ap-southeast-2.amazonaws.com/s2be/s2be-SG5006.odc-metadata.yaml

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
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-05-16/S2A_OPER_MSI_ARD_TL_VGS1_20210516T054329_A030802_T50JMS_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-06-18/S2A_OPER_MSI_ARD_TL_VGS4_20210618T022813_A031273_T54LXJ_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-06-20/S2B_OPER_MSI_ARD_TL_VGS4_20210620T015752_A022393_T55LBC_N03.00/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-07-02/S2B_OPER_MSI_ARD_TL_VGS1_20210702T024204_A022565_T53KNT_N03.01/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-07-07/S2B_OPER_MSI_ARD_TL_VGS1_20210707T014852_A022636_T54HWC_N03.01/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-07-08/S2A_OPER_MSI_ARD_TL_VGS4_20210708T022548_A031559_T54HTJ_N03.01/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-07-03/S2A_OPER_MSI_ARD_TL_VGS4_20210703T013119_A031487_T55HFB_N03.01/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-07-31/S2B_OPER_MSI_ARD_TL_VGS4_20210731T011212_A022979_T56JKT_N03.01/ARD-METADATA.yaml \
			s3://dea-public-data/L2/sentinel-2-nrt/S2MSIARD/2021-08-05/S2A_OPER_MSI_ARD_TL_VGS4_20210805T013351_A031959_T56JKT_N03.01/ARD-METADATA.yaml

metadata-s2-c3-prov:
	docker-compose exec alchemist \
		datacube metadata add \
			https://raw.githubusercontent.com/GeoscienceAustralia/dea-config/master/products/nrt/sentinel/eo_s2_nrt.odc-type.yaml

product-s2-c3-prov:
	docker-compose exec alchemist \
		datacube product add \
			https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_s2a_provisional.odc-product.yaml
	docker-compose exec alchemist \
		datacube product add \
			https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_s2b_provisional.odc-product.yaml

index-s2-c3-prov:
	docker-compose exec alchemist \
		datacube dataset add --ignore-lineage --confirm-ignore-lineage \
			s3://dea-public-data/baseline/ga_s2bm_ard_provisional_3/51/KWR/2021/09/02_nrt/20210902T033620/ga_s2bm_ard_provisional_3-2-1_51KWR_2021-09-02_nrt.odc-metadata.yaml \
			


quickstart: initdb metadata product index index-geomedian metadata-s2-nrt product-s2-nrt metadata-eo_plus index-s2-nrt product-s2be index-s2be product-s2-c3 

index-ba-bm-s2:
    docker-compose exec alchemist \
	    datacube dataset add --ignore-lineage --confirm-ignore-lineage \
		    s3://dea-public-data/derivative/ga_s2_ba_bm_3/1-6-0/54/HVE/2021/07/22/20210722T015557/ga_s2_ba_bm_3_54HVE_2021-07-22_interim.odc-metadata.yaml

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

ard-c2-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/config_ba_L3_ARD_provisional.yaml \
		--uuid 3e846ef0-5e7a-402e-b1a0-27e319ca78da

ard-c3-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/config_ba_C2_ARD_provisional.yaml \
		--uuid 5c70a4a2-cf36-4779-92a8-b35b8039cb0a

bai-one:
	docker-compose exec alchemist \
		datacube-alchemist run-one --config-file ./examples/c3_config_bai_s2be.yaml \
		--uuid 8ed63ad1-875e-4823-87f4-8431bbd1e899

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

# Africa Examples
product-africa:
	docker-compose exec alchemist \
		datacube product add \
			https://raw.githubusercontent.com/digitalearthafrica/config/master/products/ls8_sr.odc-product.yaml \
			https://raw.githubusercontent.com/digitalearthafrica/config/master/products/ls7_sr.odc-product.yaml \
			https://raw.githubusercontent.com/digitalearthafrica/config/master/products/ls5_sr.odc-product.yaml

index-africa:
	docker-compose exec --env AWS_DEFAULT_REGION=af-south-1 alchemist \
		bash -c "\
		s3-to-dc --stac --no-sign-request \
			s3://deafrica-landsat/collection02/level-2/standard/oli-tirs/2017/160/071/LC08_L2SP_160071_20170830_20200903_02_T1/*SR_stac.json \
			ls8_sr && \
		s3-to-dc --stac --no-sign-request \
			s3://deafrica-landsat/collection02/level-2/standard/etm/2021/170/052/LE07_L2SP_170052_20210316_20210412_02_T1/*_SR_stac.json \
			ls7_sr && \
		s3-to-dc --stac --no-sign-request \
			s3://deafrica-landsat/collection02/level-2/standard/tm/1994/176/044/LT05_L2SP_176044_19940714_20210402_02_T1/*_SR_stac.json \
			ls5_sr"

wo-africa-one:
	docker-compose exec \
		--env AWS_DEFAULT_REGION=af-south-1 \
		--env AWS_S3_ENDPOINT=s3.af-south-1.amazonaws.com \
		alchemist \
		datacube-alchemist run-one --config-file ./examples/wofs_ls.alchemist.yaml \
		--uuid 1f88087d-0da6-55be-aafb-5e370520e405

fc-africa-one:
	docker-compose exec \
		--env AWS_DEFAULT_REGION=af-south-1 \
		--env AWS_S3_ENDPOINT=s3.af-south-1.amazonaws.com \
		alchemist \
		datacube-alchemist run-one --config-file ./examples/fc_ls.alchemist.yaml \
		--uuid 1f88087d-0da6-55be-aafb-5e370520e405

THREE_AFRICA=1f88087d-0da6-55be-aafb-5e370520e405 272c298f-03e3-5a08-a584-41a0a3c3cb95 834d56e2-7465-5980-a6af-615ef0f67e28

wo-africa-three:
	docker-compose exec \
		--env AWS_DEFAULT_REGION=af-south-1 \
		--env AWS_S3_ENDPOINT=s3.af-south-1.amazonaws.com \
		alchemist bash -c\
			"echo '${THREE_AFRICA}' | \
			xargs -n1 datacube-alchemist run-one --config-file ./examples/wofs_ls.alchemist.yaml --uuid \
			"

fc-africa-three:
	docker-compose exec \
		--env AWS_DEFAULT_REGION=af-south-1 \
		--env AWS_S3_ENDPOINT=s3.af-south-1.amazonaws.com \
		alchemist bash -c\
			"echo '${THREE_AFRICA}' | \
			xargs -n1 datacube-alchemist run-one --config-file ./examples/fc_ls.alchemist.yaml --uuid \
			"

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
