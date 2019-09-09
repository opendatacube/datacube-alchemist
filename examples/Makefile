pullfromqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_PULLFROMQUEUE_MESSAGE_QUEUE=alchemist-standard \
	datacube-alchemist pullfromqueue

addtoqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_ADDTOQUEUE_MESSAGE_QUEUE=alchemist-standard \
	ALCHEMIST_ADDTOQUEUE_LIMIT=1 \
	ALCHEMIST_ADDTOQUEUE_ENVIRONMENT=datacube \
	ALCHEMIST_ADDTOQUEUE_CONFIG_FILE=s3://test-results-deafrica-staging-west/test_configs/DEAfrica_fc_config.yaml \
	datacube-alchemist addtoqueue
