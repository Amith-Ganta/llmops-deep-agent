# Convenience targets (Linux/macOS/Git Bash). On plain Windows PowerShell,
# run the underlying commands directly - they are listed in the README.

IMAGE ?= ghcr.io/amith-ganta/llmops-deep-agent
TAG   ?= latest

.PHONY: install dev lint test evals run frontend docker-build docker-run kind-up kind-load deploy undeploy

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

lint:
	ruff check .

test:
	pytest tests/ -v

evals:
	pytest evals/ -v

run:
	uvicorn app.main:app --reload --port 8000

frontend:
	pip install -r frontend/requirements.txt
	streamlit run frontend/app.py

docker-build:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env $(IMAGE):$(TAG)

kind-up:
	kind create cluster --config k8s/kind-config.yaml
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
	kubectl -n kube-system patch deployment metrics-server --type=json -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

kind-load:
	kind load docker-image $(IMAGE):$(TAG) --name llmops

deploy:
	kubectl create secret generic deep-agent-secrets --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install deep-agent helm/deep-agent

undeploy:
	helm uninstall deep-agent
