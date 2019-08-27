add-to-queue:
	BUCKET=deafrica-data \
	BUCKET_PATH=usgs \
	LIMIT=3 \
	AWS_DEFAULT_REGION=us-west-2 \
	QUEUE=landsat-to-wofs \
	python3 add_to_queue.py

add-to-frak:
	BUCKET=deafrica-data \
	BUCKET_PATH=usgs/ \
	LIMIT=99999 \
	AWS_DEFAULT_REGION=us-west-2 \
	QUEUE=landsat-to-frak \
	python3 add_to_queue.py

up-wofs:
	docker-compose up \
		-e TYPE=wofs \
		-e SQS_QUEUE_URL=landsat-to-wofs \
		-e OUTPUT_PATH=usgs/wofs \
	 	-e FILE_PREFIX=L8_WATER_3577

up-frak:
	docker-compose run \
		-e TYPE=frak \
		-e SQS_QUEUE_URL=landsat-to-frak \
		-e OUTPUT_PATH=usgs/frak \
		-e FILE_PREFIX=L8_FRAK_3577 \
		wofl-copter


push:
	docker build DockerFile --tag opendatacube/datacube-alchemist
	docker push opendatacube/datacube-alchemist
