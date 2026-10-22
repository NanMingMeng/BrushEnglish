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
