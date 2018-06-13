.PHONY: docker rundev

REPOSITORY=some/example/repository
export REPOSITORY
TAG := TEST

docker:
	docker build -t $(REPOSITORY):$(TAG) .

rundev: docker
	docker run --rm -p 5000:5000 --entrypoint python $(REPOSITORY):$(TAG) /app/RunController/server.py
