from conftest import SKILL_PATH

# 계약 검증은 *구조적·내구성 있는* 사실만 본다 (state/slot 이름·개수, 섹션 존재).
# 변동성 있는 산문 문구를 exact-match 하지 않는다 — 그것이 stale 의 원인이었다 (IN-0002).
# 추천 톤·trade-off·calibration 같은 행동 품질은 recommendation_eval.py 의 영역.

FIVE_STATES = ["DETECT", "INTAKE", "GATE", "PROPOSE", "DONE"]
SIX_SLOTS = ["goal", "constraint", "tech_level", "success", "deployment_target", "user_scale"]


def test_skill_keeps_five_state_contract():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert "5 fixed states" in content
    for state in FIVE_STATES:
        assert f"### {state}" in content, f"state section missing: {state}"


def test_skill_keeps_six_slot_contract():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert "6 slots" in content
    for slot in SIX_SLOTS:
        assert slot in content, f"slot missing: {slot}"


def test_skill_documents_simple_mode_and_fast_path():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert "answer_style" in content
    assert "Fast Path" in content
    assert "Simple Explain" in content
