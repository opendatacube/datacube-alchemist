#!/usr/bin/env bash
# Bail on the first error
set -ex

# Add product definitions
# Custom metadata
datacube metadata add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml
# ARD
datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls5.odc-product.yaml
datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls7.odc-product.yaml
datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ard_ls8.odc-product.yaml
# Derivatives
datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ga_ls_wo_3.odc-product.yaml
datacube product add https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/develop/digitalearthau/config/eo3/products-aws/ga_ls_fc_3.odc-product.yaml

# Index one of each ARD product (5, 7 and 8)
s3-to-dc "s3://dea-public-data/baseline/ga_ls5t_ard_3/091/084/2010/09/08/*.json" --skip-lineage --stac ga_ls5t_ard_3
s3-to-dc "s3://dea-public-data/baseline/ga_ls7e_ard_3/102/071/2020/09/09/*.json" --skip-lineage --stac ga_ls7e_ard_3
s3-to-dc "s3://dea-public-data/baseline/ga_ls8c_ard_3/094/084/2020/09/09/*.json" --skip-lineage --stac ga_ls8c_ard_3

# Run sample wofs and fc on each of the three scenes
TEST_SCENES='642e14bd-9ebb-48f0-ac6c-543aebc538c8 7e96b76a-6b02-4427-9a1d-3c9104f2db96 3b671f51-eaa0-49dc-b4f0-311c96862666'

echo ${TEST_SCENES} | xargs -n1 datacube-alchemist run-one --config-file ./examples/c3_config_wo.yaml --dryrun --uuid
echo ${TEST_SCENES} | xargs -n1 datacube-alchemist run-one --config-file ./examples/c3_config_fc.yaml --dryrun --uuid

# Index and test loading data from both? This needs a way to
# run decimated process, so it's fast, and that doesn't delete
# data.
