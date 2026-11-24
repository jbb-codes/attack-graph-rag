"""Offline checks of the Kubernetes manifests. They prove the files say the safe things
we promise (no secrets, non-root, probes, limits, wiring); only a real cluster proves they run."""

import re
from pathlib import Path

import pytest
import yaml

K8S = Path(__file__).parent.parent / "k8s"


def load_all(paths):
    return [doc for path in sorted(paths) for doc in yaml.safe_load_all(path.read_text()) if doc]


DEPLOYED = load_all(K8S.glob("*.yaml"))
ALL_FILES = [*K8S.glob("*.yaml"), *K8S.glob("examples/*.yaml")]


def of_kind(kind):
    return [d for d in DEPLOYED if d["kind"] == kind]


def pod_spec(workload):
    return workload["spec"]["template"]["spec"]


def containers(workload):
    spec = pod_spec(workload)
    return [*spec.get("initContainers", []), *spec["containers"]]


WORKLOADS = [*of_kind("Deployment"), *of_kind("Job")]
ids = lambda w: w["metadata"]["name"]  # noqa: E731


def test_every_object_lives_in_the_project_namespace():
    for doc in DEPLOYED:
        if doc["kind"] != "Namespace":
            assert doc["metadata"]["namespace"] == "attack-graph", doc["metadata"]["name"]


def test_namespace_enforces_the_restricted_pod_security_level():
    (namespace,) = of_kind("Namespace")
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"


def test_no_secret_is_applied_with_the_manifests():
    assert of_kind("Secret") == []


def test_example_secret_holds_only_a_placeholder():
    (secret,) = load_all((K8S / "examples").glob("secret*.yaml"))
    for value in secret["stringData"].values():
        assert "replace-me" in value


def test_no_file_contains_something_shaped_like_a_real_key():
    for path in ALL_FILES:
        assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", path.read_text()), path.name


def test_config_map_has_no_secret_settings():
    (config,) = of_kind("ConfigMap")
    for name in config["data"]:
        assert not re.search(r"KEY|TOKEN|SECRET|PASSWORD", name), name


def test_api_key_comes_from_a_secret_reference_not_a_literal_value():
    (app,) = [d for d in of_kind("Deployment") if ids(d) == "app"]
    (key,) = [e for e in containers(app)[0]["env"] if e["name"] == "ANTHROPIC_API_KEY"]
    assert "value" not in key
    assert key["valueFrom"]["secretKeyRef"]["key"] == "ANTHROPIC_API_KEY"


@pytest.mark.parametrize("workload", WORKLOADS, ids=ids)
def test_pods_run_as_non_root_with_default_seccomp(workload):
    context = pod_spec(workload)["securityContext"]
    assert context["runAsNonRoot"] is True
    assert context["runAsUser"] != 0
    assert context["seccompProfile"]["type"] == "RuntimeDefault"
    assert pod_spec(workload)["automountServiceAccountToken"] is False


@pytest.mark.parametrize("workload", WORKLOADS, ids=ids)
def test_containers_drop_privileges_and_set_resources(workload):
    for container in containers(workload):
        context = container["securityContext"]
        assert context["allowPrivilegeEscalation"] is False, container["name"]
        assert context["capabilities"]["drop"] == ["ALL"], container["name"]
        assert "memory" in container["resources"]["requests"], container["name"]
        assert "memory" in container["resources"]["limits"], container["name"]


@pytest.mark.parametrize("workload", WORKLOADS, ids=ids)
def test_images_are_pinned_to_a_non_latest_tag_and_never_pulled(workload):
    for container in containers(workload):
        tag = container["image"].partition(":")[2]
        assert tag and tag != "latest", container["image"]
        assert container["imagePullPolicy"] == "IfNotPresent"


@pytest.mark.parametrize("workload", of_kind("Deployment"), ids=ids)
def test_deployments_have_readiness_and_liveness_probes(workload):
    for container in workload["spec"]["template"]["spec"]["containers"]:
        assert "readinessProbe" in container
        assert "livenessProbe" in container


def test_api_probes_use_the_health_endpoint():
    (app,) = [d for d in of_kind("Deployment") if ids(d) == "app"]
    container = pod_spec(app)["containers"][0]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert container[probe]["httpGet"]["path"] == "/health"


def test_stateful_deployments_replace_pods_without_overlap():
    for name in ("sparql", "chroma"):
        (workload,) = [d for d in of_kind("Deployment") if ids(d) == name]
        assert workload["spec"]["strategy"]["type"] == "Recreate"
        assert workload["spec"]["replicas"] == 1


@pytest.mark.parametrize("workload", WORKLOADS, ids=ids)
def test_every_claimed_volume_exists(workload):
    claims = {c["metadata"]["name"] for c in of_kind("PersistentVolumeClaim")}
    for volume in pod_spec(workload)["volumes"]:
        if "persistentVolumeClaim" in volume:
            assert volume["persistentVolumeClaim"]["claimName"] in claims


def test_graph_and_vectors_are_stored_on_persistent_volumes():
    mounts = {}
    for workload in of_kind("Deployment"):
        volumes = {v["name"]: v for v in pod_spec(workload)["volumes"]}
        mounts[ids(workload)] = {
            m["mountPath"] for c in containers(workload) for m in c.get("volumeMounts", [])
            if "persistentVolumeClaim" in volumes[m["name"]]
        }
    assert "/data" in mounts["sparql"]
    assert "/chroma-data" in mounts["chroma"]


def test_services_select_pods_that_exist_and_hit_a_named_port():
    pods = {ids(w): pod_spec(w) for w in of_kind("Deployment")}
    labels = {ids(w): w["spec"]["template"]["metadata"]["labels"] for w in of_kind("Deployment")}
    for service in of_kind("Service"):
        assert service["spec"].get("type", "ClusterIP") == "ClusterIP"
        assert service["spec"]["selector"] == labels[ids(service)]
        port_names = {p["name"] for c in pods[ids(service)]["containers"] for p in c["ports"]}
        for port in service["spec"]["ports"]:
            assert port["targetPort"] in port_names


def test_config_points_at_the_services_by_name_and_port():
    (config,) = of_kind("ConfigMap")
    services = {ids(s): s["spec"]["ports"][0]["port"] for s in of_kind("Service")}
    assert config["data"]["ATTACK_GRAPH_SPARQL_URL"] == f"http://sparql:{services['sparql']}"
    assert config["data"]["ATTACK_GRAPH_CHROMA_URL"] == f"http://chroma:{services['chroma']}"


def test_setup_job_loads_then_indexes_and_waits_for_the_stores():
    (job,) = of_kind("Job")
    spec = pod_spec(job)
    assert spec["restartPolicy"] == "Never"
    assert "attack-graph load && attack-graph index" in spec["containers"][0]["command"]
    assert spec["initContainers"], "the job must wait for sparql and chroma first"
