from conftest import load_estimator_module


def test_device_max_model_exists_in_ontology():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()

    for device in estimator.all_devices(ontology):
        max_model = device.get("max_model")
        if max_model:
            assert estimator.resolve_model(max_model, ontology) is not None, device["id"]


def test_unsupported_use_cases_never_become_recommended():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()

    for device in estimator.all_devices(ontology):
        model = estimator.select_summary_model(device, ontology)
        if not model:
            continue
        summary = estimator.summarize_device_capabilities(device, model, ontology)
        good_ids = {item["id"] for item in summary["good"]}
        for use_case_id in device.get("unsupported_use_cases") or []:
            assert use_case_id not in good_ids, (device["id"], use_case_id)


def test_devices_with_explicit_supported_use_cases_do_not_recommend_out_of_scope_cases():
    estimator = load_estimator_module()
    ontology = estimator.load_ontology()

    for device in estimator.all_devices(ontology):
        supported = device.get("supported_use_cases", "all")
        if supported == "all":
            continue
        model = estimator.select_summary_model(device, ontology)
        if not model:
            continue
        summary = estimator.summarize_device_capabilities(device, model, ontology)
        good_ids = {item["id"] for item in summary["good"]}
        for use_case in ontology.get("use_cases", []):
            if use_case["id"] not in supported:
                assert use_case["id"] not in good_ids, (device["id"], use_case["id"])
