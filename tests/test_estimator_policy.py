from conftest import load_estimator_module


def test_summary_model_uses_device_max_model():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()
    device = estimator.resolve_device("mac_mini_m4_32gb", ontology)

    model = estimator.select_summary_model(device, ontology)

    assert model["id"] == "qwen3.5:35b-a3b"


def test_summary_marks_fine_tuning_as_unsupported_on_mac_mini_m4_32gb():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()
    device = estimator.resolve_device("mac_mini_m4_32gb", ontology)
    model = estimator.resolve_model("qwen3.5:35b-a3b", ontology)

    summary = estimator.summarize_device_capabilities(device, model, ontology)
    bad_ids = {item["id"] for item in summary["bad"]}

    assert "fine_tuning" in bad_ids


def test_summary_marks_web_automation_as_good_on_mac_mini_m4_32gb():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()
    device = estimator.resolve_device("mac_mini_m4_32gb", ontology)
    model = estimator.resolve_model("qwen3.5:35b-a3b", ontology)

    summary = estimator.summarize_device_capabilities(device, model, ontology)
    good_ids = {item["id"] for item in summary["good"]}

    assert "web_automation" in good_ids


def test_dense_27b_is_batch_only_for_code_review_on_mac_mini_m4_32gb():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()

    report = estimator.report_device_model("mac_mini_m4_32gb", "qwen3.5:27b", ontology)

    assert "code_review" in report
    assert "Batch/offline only" in report
