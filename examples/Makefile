pullfromqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_PULLFROMQUEUE_MESSAGE_QUEUE=alchemist-standard \
	datacube-alchemist pullfromqueue

fcaddtoqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_ADDTOQUEUE_MESSAGE_QUEUE=alchemist-standard \
	ALCHEMIST_ADDTOQUEUE_LIMIT=1 \
	ALCHEMIST_ADDTOQUEUE_ENVIRONMENT=datacube \
	ALCHEMIST_ADDTOQUEUE_CONFIG_FILE=s3://test-results-deafrica-staging-west/test_configs/DEAfrica_fc_config.yaml \
	datacube-alchemist addtoqueue

S2Afcaddtoqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_ADDTOQUEUE_MESSAGE_QUEUE=alchemist-standard \
	ALCHEMIST_ADDTOQUEUE_LIMIT=9 \
	ALCHEMIST_ADDTOQUEUE_ENVIRONMENT=datacube \
	ALCHEMIST_ADDTOQUEUE_CONFIG_FILE=fc_config_S2A.yaml \
	datacube-alchemist addtoqueue

S2Awofsaddtoqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_ADDTOQUEUE_MESSAGE_QUEUE=alchemist-standard \
	ALCHEMIST_ADDTOQUEUE_LIMIT=1 \
	ALCHEMIST_ADDTOQUEUE_ENVIRONMENT=datacube \
	ALCHEMIST_ADDTOQUEUE_CONFIG_FILE=wofs_config_S2A.yaml \
	datacube-alchemist addtoqueue

wofsnodemaddtoqueue:
	AWS_DEFAULT_REGION=us-west-2 \
	ALCHEMIST_ADDTOQUEUE_MESSAGE_QUEUE=alchemist-standard \
	ALCHEMIST_ADDTOQUEUE_LIMIT=1 \
	ALCHEMIST_ADDTOQUEUE_ENVIRONMENT=datacube \
	ALCHEMIST_ADDTOQUEUE_CONFIG_FILE=DEAfrica_wofs_no_dsm.yaml \
	datacube-alchemist addtoqueue
