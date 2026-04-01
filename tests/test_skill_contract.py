from conftest import SKILL_PATH


def test_skill_keeps_five_state_and_five_slot_contract():
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert "상태는 5개 고정" in content
    assert "슬롯은 5개" in content


def test_skill_documents_simple_mode_and_fast_path():
    content = SKILL_PATH.read_text(encoding="utf-8")

    assert "answer_style" in content
    assert "Fast Path 감지" in content
    assert "Simple Explain용" in content
    assert "다음에 좁혀볼 수 있는 것" in content
