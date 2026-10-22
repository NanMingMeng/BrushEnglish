import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "完整脚本_学习测试循环.py"

spec = importlib.util.spec_from_file_location("brush_engine_under_test", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)


def test_split_pos_and_cn():
    pos, parts = engine._split_pos_and_cn("n. 恶棍；a. 强硬的")
    assert "n" in pos
    assert "adj" in pos
    assert "恶棍" in parts


def test_exact_containment_match():
    meaning = "n.预测，预报V.预示"
    options = ["n. 【音】短号", "v.遮盖；掩饰", "v.狼吞虎咽地吃,吞食", "n 预测预报"]
    idx, score = engine.fuzzy_option_match(meaning, options)
    assert idx == 3
    assert score >= 0.99


def test_unique_pos_fallback():
    meaning = "n. 恶棍；a. 强硬的，艰苦的，坚固的，坚韧的，粗暴的，咬不动的"
    options = [
        "v.表示，意指",
        "v.给…起别名（或绰号）",
        "v.控告，起诉，指控",
        "adj.困难的，难对付的；坚强的，能吃苦耐劳的；健...",
    ]
    idx, score = engine.fuzzy_option_match(meaning, options)
    assert idx == 3
    assert score >= 0.40


def test_dictionary_lookup_from_bank():
    meaning, source = engine.lookup_word_meaning("haste", None)
    assert meaning
    assert source == "总题库"


def test_dictionary_lookup_missing_word():
    meaning, source = engine.lookup_word_meaning("adi", None)
    assert meaning is None
    assert source is None


def test_coordinate_scaling():
    old_x, old_y = engine.SCALE_X, engine.SCALE_Y
    try:
        engine.SCALE_X, engine.SCALE_Y = 2.0, 1.5
        assert engine.scale_point((100, 200)) == (200, 300)
        assert engine.scale_region((10, 20, 30, 40)) == (20, 30, 60, 60)
    finally:
        engine.SCALE_X, engine.SCALE_Y = old_x, old_y


def test_dry_run_blocks_click_key_type_move(monkeypatch):
    old_dry_run = engine.DRY_RUN
    calls = []
    try:
        engine.DRY_RUN = True
        monkeypatch.setattr(engine.pyautogui, "click", lambda *a, **k: calls.append("click"))
        monkeypatch.setattr(engine.pyautogui, "moveTo", lambda *a, **k: calls.append("moveTo"))
        monkeypatch.setattr(engine.pyautogui, "typewrite", lambda *a, **k: calls.append("typewrite"))
        monkeypatch.setattr(engine.keyboard, "press_and_release", lambda *a, **k: calls.append("key"))

        assert engine.supervised_click(100, 200, "测试点击") is True
        assert engine.supervised_key("enter", "测试按键") is True
        engine._type_word("apple")
        engine.curve_move_to(300, 400)
        engine._move_away()

        assert calls == []
    finally:
        engine.DRY_RUN = old_dry_run


def test_screen_word_prefers_known_group_word(monkeypatch):
    monkeypatch.setattr(engine, "TEST_WORD_REGION", None)
    monkeypatch.setattr(engine, "REGION_QUESTION_TYPE", (0, 0, 100, 200))
    monkeypatch.setattr(engine, "REGION_OPTION", [(1400, 388, 1900, 440)])
    monkeypatch.setattr(engine, "ONECLASS_X_MIN", 1000)
    monkeypatch.setattr(engine, "ocr_full_screen", lambda: [
        {"text": "Rapid", "x": 1120, "y": 210},
        {"text": "hello", "x": 1500, "y": 250},
        {"text": "world", "x": 1500, "y": 300},
    ])

    word_dict = {"1": {"word": "hello", "meaning": "int. 喂"}}
    assert engine.ocr_screen_word(word_dict) == "hello"
