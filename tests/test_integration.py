from subprocess import call

import pytest


@pytest.fixture(scope="module")
def used_products() -> None:
    rv = call(["datacube", "system", "init"])
    assert rv == 0
    raw_url = "https://raw.githubusercontent.com/GeoscienceAustralia/digitalearthau/"
    # Custom metadata.
    rv = call(
        [
            "datacube",
            "metadata",
            "add",
            f"{raw_url}/develop/digitalearthau/config/eo3/eo3_landsat_ard.odc-type.yaml",
        ]
    )
    assert rv == 0
    aws_product_base = f"{raw_url}/develop/digitalearthau/config/eo3/products-aws"

    rv = call(
        [
            "datacube",
            "product",
            "add",
            # ARD.
            f"{aws_product_base}/ard_ls5.odc-product.yaml",
            f"{aws_product_base}/ard_ls7.odc-product.yaml",
            f"{aws_product_base}/ard_ls8.odc-product.yaml",
            # Derivatives
            f"{aws_product_base}/ga_ls_wo_3.odc-product.yaml",
            f"{aws_product_base}/ga_ls_fc_3.odc-product.yaml",
        ]
    )
    assert rv == 0
    # Index one of each ARD product (5, 7 and 8)
    for s3_url, product in [
        (
            "s3://dea-public-data/baseline/ga_ls5t_ard_3/091/084/2010/09/08/*.json",
            "ga_ls5t_ard_3",
        ),
        (
            "s3://dea-public-data/baseline/ga_ls7e_ard_3/102/071/2020/09/09/*.json",
            "ga_ls7e_ard_3",
        ),
        (
            "s3://dea-public-data/baseline/ga_ls8c_ard_3/094/084/2020/09/09/*.json",
            "ga_ls8c_ard_3",
        ),
    ]:
        rv = call(
            [
                "s3-to-dc",
                s3_url,
                "--no-sign-request",
                "--skip-lineage",
                "--stac",
                product,
            ]
        )
        assert rv == 0


@pytest.mark.parametrize(
    "scene",
    [
        "642e14bd-9ebb-48f0-ac6c-543aebc538c8",
        "7e96b76a-6b02-4427-9a1d-3c9104f2db96",
        "3b671f51-eaa0-49dc-b4f0-311c96862666",
    ],
)
def test_wofs_and_fc(
    monkeypatch, used_products: None, run_alchemist, scene: str
) -> None:
    monkeypatch.setenv("AWS_NO_SIGN_REQUEST", "YES")
    for config in ["./examples/c3_config_wo.yaml", "./examples/c3_config_fc.yaml"]:
        args = [
            "run-one",
            f"--config-file={config}",
            "--dryrun",
            f"--uuid={scene}",
        ]
        rv = run_alchemist(args)
        lines = [line for line in rv.output.split("\n") if "Task complete" in line]
        assert len(lines) == 1
        assert f"UUID('{scene}')" in lines[0]
