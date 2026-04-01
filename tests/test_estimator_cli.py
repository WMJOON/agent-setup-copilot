from conftest import run_estimator


def test_simple_summary_cli_contains_expected_sections():
    output = run_estimator("--device", "mac_mini_m4_32gb", "--summary-style", "simple")

    assert "한 줄 결론" in output
    assert "잘하는 것" in output
    assert "애매한 것" in output
    assert "비추천" in output
    assert "추천 기본 모델" in output


def test_compare_models_cli_still_works():
    output = run_estimator("--device", "mac_mini_m4_32gb", "--compare-models")

    assert "=== Model Comparison" in output
    assert "qwen3.5:35b-a3b" in output


def test_device_model_cli_still_works():
    output = run_estimator("--device", "mac_mini_m4_32gb", "--model", "qwen3.5:35b-a3b")

    assert "=== Performance Estimate ===" in output
    assert "Use Case Suitability" in output
