include config/lab.env
.DEFAULT_GOAL := help
KARMADA_CONFIG ?= $(PWD)/.runtime/karmada/karmada-apiserver.config
IMAGE ?= karmada-lab/placement-demo:0.1.0
.NOTPARALLEL: bootstrap
.PHONY: help bootstrap preflight kind-up karmada-up metrics-up verify-fhpa build load deploy inspect calibrate manual auto-start auto-stop verify-names
help:
	@echo 'make kind-up       Create four named kind clusters + FreeLens kubeconfigs'
	@echo 'make karmada-up    Karmada v1.19.1 init/join (karmadactl required)'
	@echo 'make bootstrap     Create clusters, Karmada, and ALL FederatedHPA dependencies'
	@echo 'make metrics-up    Install and verify member metrics-server + Karmada metrics-adapter'
	@echo 'make verify-fhpa   Check metrics API and FederatedHPA readiness'
	@echo 'make calibrate     Reserve CPU requests for target slot counts 4/6/12'
	@echo 'make build load deploy   Build and propagate demo app and Service'
	@echo 'make manual        Manual burst 4->8->10->16->22->8->4'
	@echo 'make auto-start    Install FederatedHPA + per-cluster load generation'
	@echo 'make auto-stop     Disable load generators and FederatedHPA'
	@echo 'make preflight     Check host CLI versions and Docker availability'
	@echo 'make verify-names Enforce naming contract'
bootstrap: preflight kind-up karmada-up metrics-up
	@echo 'Bootstrap incomplete: Alloy and the observability stack are not yet implemented.' >&2
	@exit 1
kind-up:
	./scripts/create-kind.sh
karmada-up:
	./scripts/init-karmada.sh
metrics-up:
	./scripts/install-resource-metrics.sh
verify-fhpa:
	./scripts/verify-fhpa-prereqs.sh
preflight: verify-names
	./scripts/preflight.sh
build:
	docker build -t $(IMAGE) app/
load:
	@for c in $(DC_PRIMARY) $(DC_SECONDARY) $(CLOUD_CLUSTER); do kind load docker-image $(IMAGE) --name $$c; done
deploy:
	@for c in $(DC_PRIMARY) $(DC_SECONDARY) $(CLOUD_CLUSTER); do \
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
auto-start:
	./scripts/run-auto.sh
auto-stop:
	./scripts/stop-auto.sh
verify-names:
	python3 scripts/check_cluster_names.py
