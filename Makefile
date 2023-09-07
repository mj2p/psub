ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

cover:
	pipenv run coverage run; pipenv run coverage html

checks:
	pipenv run pre-commit run -a
