include config/lab.env
.DEFAULT_GOAL := help
KARMADA_CONFIG ?= $(PWD)/.runtime/karmada/karmada-apiserver.config
IMAGE ?= karmada-lab/placement-demo:0.1.0
.NOTPARALLEL: bootstrap up
.PHONY: help up down bootstrap verify preflight kind-up karmada-up metrics-up verify-fhpa observability-backends observability-collectors placement-exporter verify-observability prepare-demo build load deploy inspect calibrate manual demo-manual demo-auto reset-demo auto-start auto-stop verify-names
help:
	@echo 'make kind-up       Create four named kind clusters + FreeLens kubeconfigs'
	@echo 'make karmada-up    Karmada v1.19.1 init/join (karmadactl required)'
	@echo 'make up            Reconcile the lab and run current health checks'
	@echo 'make down          Delete only lab-recorded kind clusters and their local PVC data'
	@echo 'make verify        Check cluster, metrics, telemetry and workload health'
	@echo 'make metrics-up    Install and verify member metrics-server + Karmada metrics-adapter'
	@echo 'make verify-fhpa   Check metrics API and FederatedHPA readiness'
	@echo 'make observability-backends Install the central monitoring backends (collection not included)'
	@echo 'make observability-collectors Install Alloy and kube-state-metrics in all four clusters'
	@echo 'make placement-exporter Install the read-only Karmada placement exporter'
	@echo 'make verify-observability Check backend readiness and four metrics sources'
	@echo 'make calibrate     Reserve CPU requests for target slot counts 4/6/12'
	@echo 'make build load deploy   Build and propagate demo app and Service'
	@echo 'make demo-manual   Manual burst 4->8->10->16->22->8->4'
	@echo 'make reset-demo    Stop HPA/load and restore four Ready replicas'
	@echo 'make demo-auto     Run bounded FederatedHPA burst, scale-in and reset'
	@echo 'make auto-stop     Disable load generators and FederatedHPA'
	@echo 'make preflight     Check host CLI versions and Docker availability'
	@echo 'make verify-names Enforce naming contract'
up: bootstrap
down:
	./scripts/down.sh
bootstrap: preflight kind-up karmada-up metrics-up observability-backends placement-exporter observability-collectors prepare-demo verify
	@echo 'Lab reconciliation and current health checks passed; scenario and fresh-install results are recorded separately.'
kind-up:
	./scripts/create-kind.sh
karmada-up:
	./scripts/init-karmada.sh
metrics-up:
	./scripts/install-resource-metrics.sh
verify-fhpa:
	./scripts/verify-fhpa-prereqs.sh
observability-backends: verify-names
	./scripts/install-observability-backends.sh
observability-collectors: verify-names
	./scripts/install-collectors.sh
placement-exporter: verify-names
	./scripts/install-placement-exporter.sh
verify-observability: verify-names
	./scripts/verify-observability.sh
prepare-demo: verify-names
	./scripts/prepare-demo.sh
verify: verify-names
	./scripts/verify-lab.sh
preflight: verify-names
	./scripts/preflight.sh
build:
	docker build --provenance=false -t $(IMAGE) app/
load:
	@set -e; for c in $(DC_PRIMARY) $(DC_SECONDARY) $(CLOUD_CLUSTER); do kind load docker-image $(IMAGE) --name $$c; done
deploy:
	@set -e; for c in $(DC_PRIMARY) $(DC_SECONDARY) $(CLOUD_CLUSTER); do \
	  kubectl --context "kind-$$c" create namespace demo --dry-run=client -o yaml | kubectl --context "kind-$$c" apply -f -; \
	done
	kubectl --kubeconfig $(KARMADA_CONFIG) apply -f karmada/placement-demo.yaml
	kubectl --kubeconfig $(KARMADA_CONFIG) apply -f karmada/service.yaml
	kubectl --kubeconfig $(KARMADA_CONFIG) apply -f karmada/overflow-policy.yaml
	kubectl --kubeconfig $(KARMADA_CONFIG) apply -f karmada/service-propagation.yaml
calibrate:
	python3 scripts/calibrate-capacity.py
inspect:
	kubectl --kubeconfig $(KARMADA_CONFIG) -n demo get deployment,service,resourcebinding,federatedhpa
manual:
	./scripts/run-manual.sh
demo-manual: manual
reset-demo:
	./scripts/reset-demo.sh
auto-start:
	./scripts/run-auto.sh
demo-auto: auto-start
auto-stop:
	./scripts/stop-auto.sh
verify-names:
	python3 scripts/check_cluster_names.py
