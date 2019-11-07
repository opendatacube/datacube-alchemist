
test:
	pytest tests

docker-test:
	docker build . --tag opendatacube/datacube-alchemist
	docker run opendatacube/datacube-alchemist -- pytest tests

push:
	docker build . --tag opendatacube/datacube-alchemist
	docker push opendatacube/datacube-alchemist

test-push:
	docker build . --tag opendatacube/datacube-alchemist-test
	docker push opendatacube/datacube-alchemist-test
