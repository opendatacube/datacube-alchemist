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

push:
	docker build . --tag opendatacube/datacube-alchemist:unstable-1.0.2
	docker push opendatacube/datacube-alchemist:unstable-1.0.2
