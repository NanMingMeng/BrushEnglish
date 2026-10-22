#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OneClass 完整脚本：学习→识别→测试 循环（增强版）
===================================================
功能：
- 配置文件化（config.json）
- 详细日志系统（文件 + 控制台 + 时长前缀）
- 断点续传（progress.json）
- 运行统计
- OCR失败自动重试
- 反检测增强（休息/曲线鼠标/可配置错误率）
- 页面状态检测与异常兜底
"""

import os, io, re, time, json, base64, urllib.request, threading, ctypes, random, sys, logging, shutil
from datetime import datetime, timedelta
from pathlib import Path
from difflib import SequenceMatcher
from logging.handlers import RotatingFileHandler

import keyboard, pyautogui
from PIL import Image, ImageGrab

# ---------- 拼写题「听音」用的两个库（没装也不影响其它功能） ----------
# soundcard      ：负责录电脑里播放的声音（不是麦克风，是系统内部的声音）
# faster_whisper ：负责把录到的英语发音转成文字
try:
    import soundcard as sc
    _SOUNDCARD_AVAILABLE = True
except Exception:
    _SOUNDCARD_AVAILABLE = False
    sc = None
try:
    from faster_whisper import WhisperModel as _WhisperModel
    _FASTER_WHISPER_AVAILABLE = True
except Exception:
    _FASTER_WHISPER_AVAILABLE = False
    _WhisperModel = None
_ASR_AVAILABLE = _SOUNDCARD_AVAILABLE and _FASTER_WHISPER_AVAILABLE


# ================= 基础路径 =================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
PROGRESS_PATH = BASE_DIR / "progress.json"
STATS_PATH = BASE_DIR / "stats.json"
LOG_DIR = BASE_DIR / "logs"
SAVE_DIR = BASE_DIR / "学习截图"
WORD_DICT = str(BASE_DIR / "word_dict_umi.json")
WORD_BANK = str(BASE_DIR / "四级英语新大纲词汇表.json")
SCREENSHOT_DIR = BASE_DIR / "测试截图"
MONITOR_STATE_FILE = BASE_DIR / "monitor_state.json"
MONITOR_ACTION_FILE = BASE_DIR / "monitor_action.json"
MONITOR_INPUT_FILE = BASE_DIR / "monitor_input.json"
SCREENSHOT_DIR.mkdir(exist_ok=True)
SAVE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


# ================= 配置加载 =================
def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

CONFIG = load_config()

# ================= 坐标自适应（分辨率 / DPI 缩放） =================
# 基准分辨率：配置里的坐标默认按 1920x1080、100% 缩放下采集。
# 换屏幕或改缩放后，pyautogui.size() 会返回新的逻辑分辨率，这里按比例换算。
_SCREEN_CFG = CONFIG.get("screen", {}) or {}
BASE_SCREEN_W = int(_SCREEN_CFG.get("base_width", 1920) or 1920)
BASE_SCREEN_H = int(_SCREEN_CFG.get("base_height", 1080) or 1080)
AUTO_SCALE_COORDS = bool(_SCREEN_CFG.get("auto_scale", True))
DRY_RUN = bool(CONFIG.get("dry_run", False))


def _current_screen_size():
    try:
        w, h = pyautogui.size()
        if w > 0 and h > 0:
            return int(w), int(h)
    except Exception:
        pass
    return BASE_SCREEN_W, BASE_SCREEN_H


SCREEN_W, SCREEN_H = _current_screen_size()
SCALE_X = (SCREEN_W / BASE_SCREEN_W) if (AUTO_SCALE_COORDS and BASE_SCREEN_W) else 1.0
SCALE_Y = (SCREEN_H / BASE_SCREEN_H) if (AUTO_SCALE_COORDS and BASE_SCREEN_H) else 1.0


def _sx(v):
    return int(round(float(v) * SCALE_X))


def _sy(v):
    return int(round(float(v) * SCALE_Y))


def scale_point(p):
    """把基准分辨率下的点击坐标换算成当前分辨率。"""
    return (_sx(p[0]), _sy(p[1]))


def scale_region(r):
    """把基准分辨率下的 OCR 区域换算成当前分辨率。"""
    x1, y1, x2, y2 = r
    return (_sx(x1), _sy(y1), _sx(x2), _sy(y2))


UMI_OCR_URL = CONFIG.get("umi_ocr", {}).get("url", "http://127.0.0.1:1224/api/ocr")
UMI_OCR_TIMEOUT = CONFIG.get("umi_ocr", {}).get("timeout", 10)
UMI_OCR_RETRY = CONFIG.get("umi_ocr", {}).get("retry_times", 3)
UMI_OCR_RETRY_DELAY = CONFIG.get("umi_ocr", {}).get("retry_delay", 0.5)

GROUP_SIZE = CONFIG.get("group_size", 30)
FUZZY_TYPE_THRESHOLD = CONFIG.get("fuzzy", {}).get("type_threshold", 0.45)
FUZZY_OPTION_THRESHOLD = CONFIG.get("fuzzy", {}).get("option_threshold", 0.35)
IMAGE_DETECT_ENABLED = CONFIG.get("image_detect_enabled", True)

LEARN = CONFIG.get("regions", {}).get("learn", {})
TEST = CONFIG.get("regions", {}).get("test", {})

BTN_VIEW = scale_point(LEARN.get("btn_view", [1675, 432]))
BTN_EASY = scale_point(LEARN.get("btn_easy", [1846, 210]))
BTN_CONTINUE_LEARN = scale_point(LEARN.get("btn_continue_learn", [1685, 945]))
LEARN_NEXT = scale_point(LEARN.get("learn_next", [1679, 943]))
REGION_WORD = scale_region(LEARN.get("word", [1467, 188, 1799, 290]))
REGION_MEAN = scale_region(LEARN.get("meaning", [1480, 399, 1914, 596]))
REGION_TODAY = scale_region(LEARN.get("today", [1632, 95, 1735, 160]))
REGION_WORD_INDEX = scale_region(LEARN.get("word_index", [1294, 371, 1400, 410]))

INPUT_SPELL = scale_point(TEST.get("input_spell", [1675, 378]))
BTN_CONFIRM = scale_point(TEST.get("btn_confirm", [1680, 465]))
TEST_NEXT = scale_point(TEST.get("test_next", [1679, 980]))
BTN_FINISH = scale_point(TEST.get("btn_finish", [1670, 980]))
BTN_BACK = scale_point(TEST.get("btn_back", [1470, 50]))
BTN_TASK = scale_point(TEST.get("btn_task", [1055, 400]))
BTN_AGAIN = scale_point(TEST.get("btn_again", [1800, 960]))
OPT_COORDS = [scale_point(c) for c in TEST.get("option_coords", [[1680,420],[1680,500],[1680,580],[1680,650]])]
REGION_NUMBER = scale_region(TEST.get("number", [1457, 99, 1616, 134]))
# 测试页「目标单词」区域：用来认屏幕上真正的单词。没校准过时为 None，自动全屏定位
TEST_WORD_REGION = scale_region(TEST.get("word_region")) if TEST.get("word_region") else None
REGION_QUESTION_TYPE = scale_region(TEST.get("question_type", [1463, 167, 1632, 200]))
REGION_OPTION = [scale_region(r) for r in TEST.get("option_regions", [
    (1465,388,1895,440),(1465,468,1895,520),
    (1465,545,1895,597),(1465,619,1895,671),
])]

ANTI = CONFIG.get("anti_detect", {})
FAIL_RATE = ANTI.get("fail_rate", 0.07)
HESITATE_RATE = ANTI.get("hesitate_rate", 0.15)
REVIEW_RATE = ANTI.get("review_rate", 0.2)
READ_TIME_RANGE = tuple(ANTI.get("read_time_range", [1.0, 3.0]))
OP_DELAY_RANGE = tuple(ANTI.get("operation_delay_range", [0.5, 1.5]))
LEARN_READ_RANGE = tuple(ANTI.get("learn_read_time_range", [0.8, 2.0]))
LEARN_CLICK_RANGE = tuple(ANTI.get("learn_click_delay_range", [0.3, 0.8]))
REST_ENABLED = ANTI.get("rest_between_rounds", {}).get("enabled", True)
REST_MIN = ANTI.get("rest_between_rounds", {}).get("min_seconds", 60)
REST_MAX = ANTI.get("rest_between_rounds", {}).get("max_seconds", 200)
RANDOM_BREAK_ENABLED = ANTI.get("random_break", {}).get("enabled", True)
BREAK_INTERVAL_MIN = ANTI.get("random_break", {}).get("interval_min_questions", 10)
BREAK_INTERVAL_MAX = ANTI.get("random_break", {}).get("interval_max_questions", 20)
BREAK_MIN = ANTI.get("random_break", {}).get("break_min_seconds", 10)
BREAK_MAX = ANTI.get("random_break", {}).get("break_max_seconds", 45)
MOUSE_CURVE = ANTI.get("mouse_curve", True)

# ================= 智能精简学习（词典已收录的词跳过识别） =================
SMART = CONFIG.get("smart_learn", {})
SMART_ENABLED = SMART.get("enabled", True)
# 跳过某个词的前提＝这个词自己已确定（词条 confirmed=true，或整本词典已确认）
SMART_REQUIRE_CONFIRMED = SMART.get("require_confirmed_word", SMART.get("require_confirmed_dict", True))
# 新 OCR 识别到的词是否直接标为「已确定」（false=先存着，下次再刷到会重新 OCR 校验）
SMART_AUTO_CONFIRM_NEW = SMART.get("auto_confirm_new_words", False)
SMART_PROGRESS_OCR_EVERY_N = int(SMART.get("progress_ocr_every_n", 7) or 0)
SMART_AUTO_CONFIRM_BANK = SMART.get("auto_confirm_bank", True)
SMART_FAST_WAITS = SMART.get("fast_waits", True)
SMART_CONTINUE_WAIT = float(SMART.get("continue_wait_sec", 1.2))
SMART_FINISH_WAIT = float(SMART.get("finish_wait_sec", 1.5))
SMART_SPELL_CONFIRM_WAIT = float(SMART.get("spelling_confirm_wait_sec", 4))
SMART_TEST_NEXT_WAIT = (float(SMART.get("test_next_wait_min", 1.0)), float(SMART.get("test_next_wait_max", 2.0)))
SMART_QN_NONE_RETRIES = int(SMART.get("qn_none_retries", 3))
SMART_QN_NONE_RETRY_WAIT = float(SMART.get("qn_none_retry_wait_sec", 2.5))

# ================= 拼写题「对错反馈」读取 =================
# 答完一道拼写题点确认后，屏幕会显示答对/答错；答错时往往还会把正确拼写显示出来。
# 把它读回来，就能知道脚本猜的词对不对，进而算出「词表错位了几个」并自动纠偏。
FB = CONFIG.get("answer_feedback", {})
FB_ENABLED = bool(FB.get("enabled", True))
# probe_only=true：只记录+打日志，不改答题行为（先摸清屏幕到底显示什么）
FB_PROBE_ONLY = bool(FB.get("probe_only", True))
FB_REGION = scale_region(FB["region"]) if FB.get("region") else None
FB_WAIT = float(FB.get("wait_sec", 0.8))
FB_RIGHT_KW = [str(k) for k in FB.get("right_keywords", [])]
FB_WRONG_KW = [str(k) for k in FB.get("wrong_keywords", [])]
FB_RECORD_PATH = LOG_DIR / "拼写反馈记录.jsonl"
# 本次测试运行内记住「题号 -> 屏幕反馈的正确词」，同一题再出现时直接填它
_RETRY_WORDS = {}

# 屏幕分区：助手窗口占左半边(x<960)，OneClass答题页占右半边(x>=1000)。
# 全屏OCR必须过滤掉助手窗口的文字，否则会认到"内置 Rapid""非故意答错率"这类界面文字。
ONECLASS_X_MIN = _sx(1000)
FB_SAVE_SHOT = bool(FB.get("save_screenshot", True))
# 反馈截图单独放子目录：测试开始时清理旧截图不会连它一起删掉
FB_SHOT_DIR = SCREENSHOT_DIR / "反馈截图"
try:
    FB_SHOT_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# ================= 拼写题「听音识别」配置 =================
# 拼写题是听力题：屏幕上只有输入框，没有单词。所以要靠「听」——
# 录一段 App 自动播放的读音，用语音识别转成英文单词，再去本组词表里核对。
ASR = CONFIG.get("asr", {})
ASR_MODEL = str(ASR.get("model", "base.en"))          # 语音识别模型，base.en 约 140MB；想更准可改 small.en（约 460MB）
ASR_RECORD_SEC = float(ASR.get("record_sec", 3.0))      # 每次录几秒（最长的四级单词读一遍约 2~3 秒）
ASR_REPLAY_ON_FAIL = bool(ASR.get("replay_on_fail", True))        # 第一次没听准就点喇叭重播再听一次
ASR_FALLBACK_TO_WORDLIST = bool(ASR.get("fallback_to_wordlist", True))  # 两次都不行就退回「词表顺序」
ASR_DEVICE = ASR.get("device", None)                   # 录音设备名，留空 = 自动挑一个能录系统声音的
ASR_MATCH_CUTOFF = float(ASR.get("match_cutoff", 0.8))  # 听出来的词跟词表做模糊比对的相似度门槛
# 拼写题答案来源：asr = 听音识别（失败自动退回词表）；wordlist = 不用听音，直接按词表顺序填
SPELLING_SOURCE = str(CONFIG.get("spelling_source", "asr")).strip().lower()
_spk = TEST.get("btn_speaker_replay")                   # 拼写题界面上那个「喇叭」图标的坐标
BTN_SPEAKER_REPLAY = scale_point(_spk) if _spk else None

LOG_CFG = CONFIG.get("logging", {})
LOG_ENABLED = LOG_CFG.get("enabled", True)
LOG_LEVEL = LOG_CFG.get("level", "DEBUG")
LOG_MAX_SIZE = LOG_CFG.get("max_file_size_mb", 50) * 1024 * 1024
LOG_BACKUP_COUNT = LOG_CFG.get("backup_count", 5)
LOG_TO_FILE = LOG_CFG.get("log_to_file", True)
LOG_TO_CONSOLE = LOG_CFG.get("log_to_console", True)
LOG_ELAPSED_PREFIX = LOG_CFG.get("show_elapsed_prefix", True)

HOTKEYS = CONFIG.get("hotkeys", {})
HK_STOP = HOTKEYS.get("stop", "esc")
HK_PAUSE = HOTKEYS.get("pause", "space")
HK_SAVE = HOTKEYS.get("save_progress", "f5")


# ================= 词典题库系统 =================
BANK_DIR = BASE_DIR / "题库"
BANK_DIR.mkdir(exist_ok=True)
RUN_RECORD_DIR = BANK_DIR / "运行记录"          # 脚本每次运行记录的词典按日期归档到这里
RUN_RECORD_DIR.mkdir(exist_ok=True)
CURRENT_DICT_FILE = BANK_DIR / "当前词典.txt"     # 当前词典记录（已迁移到「题库」文件夹）
LEGACY_CURRENT_DICT_FILE = BASE_DIR / "当前词典.txt"

def _migrate_current_dict_file():
    """把旧位置的「当前词典.txt」搬进「题库」文件夹（只在首次运行时搬一次）"""
    try:
        if LEGACY_CURRENT_DICT_FILE.exists() and not CURRENT_DICT_FILE.exists():
            shutil.move(str(LEGACY_CURRENT_DICT_FILE), str(CURRENT_DICT_FILE))
            log.info(f"[词典] 词典记录文件已迁移到题库文件夹: {CURRENT_DICT_FILE}")
    except Exception as e:
        log.warning(f"[词典] 词典记录文件迁移失败（不影响使用）: {e}")

_migrate_current_dict_file()

# 词典名称检测区域（在学习页面显示词典名称的位置）
REGION_DICT_NAME = scale_region(LEARN.get("dict_name", [1480, 130, 1914, 180]))

def detect_dictionary_name():
    """
    检测当前学习的词典名称
    返回词典名称字符串，检测失败返回 None
    """
    # 尝试从文件读取上次记录的词典名称
    if CURRENT_DICT_FILE.exists():
        try:
            with open(CURRENT_DICT_FILE, 'r', encoding='utf-8') as f:
                name = f.read().strip()
            if name:
                log.info(f"[词典] 从文件读取: {name}")
                return name
        except Exception as e:
            log.warning(f"[词典] 读取文件失败: {e}")
    
    # 尝试OCR识别词典名称区域
    try:
        text = ocr_region(REGION_DICT_NAME)
        if text and len(text) > 2:
            # 清理文本
            name = text.strip().replace('\n', ' ').replace('\\', '/')
            # 过滤掉常见的非词典名称内容
            if any(kw in name for kw in ["词汇表", "单词", "词库", "词典", "四级", "六级", "考研", "雅思", "托福"]):
                log.info(f"[词典] OCR识别: {name}")
                # 保存到文件
                with open(CURRENT_DICT_FILE, 'w', encoding='utf-8') as f:
                    f.write(name)
                return name
    except Exception as e:
        log.warning(f"[词典] OCR识别失败: {e}")
    
    
    log.warning("[词典] 无法检测词典名称，使用默认名称")
    return "默认词汇表"

def get_bank_path(dict_name):
    """获取题库文件路径"""
    # 清理文件名
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', dict_name)
    return BANK_DIR / f"题库_{safe_name}.json"

def load_dictionary_bank(dict_name):
    """
    加载指定词典的题库
    返回: {"dictionary_name": "...", "total_words": 2862, "words": [...]}
    """
    bank_path = get_bank_path(dict_name)
    if bank_path.exists():
        try:
            with open(bank_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 兼容旧题库：补充缺失字段
            if "confirmed" not in data:
                data["confirmed"] = False
            if "expected_total" not in data:
                data["expected_total"] = 2862
            word_count = len(data.get("words", []))
            status = "已确认" if data.get("confirmed") else "未确认/残缺"
            log.info(f"[题库] 已加载 '{dict_name}' 题库: {word_count} 词 ({status})")
            return data
        except Exception as e:
            log.error(f"[题库] 加载失败: {e}")
    else:
        log.info(f"[题库] '{dict_name}' 暂无题库，将创建新题库")
    
    # 返回空题库结构
    return {
        "dictionary_name": dict_name,
        "total_words": 0,
        "words": [],
        "confirmed": False,
        "expected_total": 2862
    }

def save_dictionary_bank(dict_name, bank_data):
    """保存词典题库"""
    bank_path = get_bank_path(dict_name)
    try:
        with open(bank_path, 'w', encoding='utf-8') as f:
            json.dump(bank_data, f, indent=2, ensure_ascii=False)
        word_count = len(bank_data.get("words", []))
        log.info(f"[题库] 已保存 '{dict_name}' 题库: {word_count} 词")
        return True
    except Exception as e:
        log.error(f"[题库] 保存失败: {e}")
        return False

def add_word_to_bank(bank_data, global_index, word, meaning):
    """添加/更新单词到题库

    新词条带一个「已确定」标记 confirmed：
      - 已确定的词 = 以后刷到直接取用，跳过截图+OCR
      - 未确定的词 = 下次刷到仍会 OCR 校验/纠错
    新词默认是否直接算已确定，由 config.json 的 smart_learn.auto_confirm_new_words 决定。
    """
    words = bank_data.get("words", [])
    
    # 检查是否已存在
    for w in words:
        if w.get("index") == global_index:
            # 更新已有单词（保留它原来的确定状态；若本次 OCR 读出的内容变了，重置为未确定）
            changed = (w.get("word") != word) or (w.get("meaning") != meaning)
            w["word"] = word
            w["meaning"] = meaning
            if changed and not SMART_AUTO_CONFIRM_NEW:
                w["confirmed"] = False
            else:
                w.setdefault("confirmed", bool(SMART_AUTO_CONFIRM_NEW))
            return
    
    # 添加新单词
    words.append({
        "index": global_index,
        "word": word,
        "meaning": meaning,
        "confirmed": bool(SMART_AUTO_CONFIRM_NEW)
    })
    
    # 按index排序，确保顺序
    words.sort(key=lambda x: x.get("index", 0))
    bank_data["words"] = words
    bank_data["total_words"] = len(words)

def get_word_from_bank(bank_data, global_index):
    """从题库获取指定位置的单词"""
    words = bank_data.get("words", [])
    for w in words:
        if w.get("index") == global_index:
            return w
    return None

def has_bank_for_dict(dict_name):
    """检查是否有该词典的题库"""
    bank_path = get_bank_path(dict_name)
    return bank_path.exists()


def is_word_skip_enabled(bank_data):
    """逐词精简的总开关：开着 + 题库里有词

    这只是「允许逐词取用」的总闸；具体某个词跳不跳，
    由这个词自己的确定状态决定（见 get_recorded_word）。
    """
    if not SMART_ENABLED:
        return False
    if not bank_data or not bank_data.get("words"):
        return False
    return True


def count_confirmed_words(bank_data):
    """统计题库里有多少词已处于「已确定」状态"""
    try:
        if not bank_data:
            return 0
        words = bank_data.get("words", []) or []
        if bank_data.get("confirmed", False):
            return len(words)      # 整本已确认 = 所有词都算已确定
        return sum(1 for w in words if w.get("confirmed"))
    except Exception:
        return 0


def is_word_confirmed(bank_data, word_entry):
    """判断某个词条自身是否已确定（整本 confirmed 也算）"""
    try:
        if not bank_data or not word_entry:
            return False
        if bank_data.get("confirmed", False):
            return True
        return bool(word_entry.get("confirmed", False))
    except Exception:
        return False


def is_bank_trusted(bank_data):
    """该词典库是否「整本可信」（可以直接取词、跳过OCR，并启用更激进的等待精简）
    规则：精简开关开着 + 题库非空 + （需要确认时）题库已标记 confirmed
    """
    if not SMART_ENABLED:
        return False
    if not bank_data or not bank_data.get("words"):
        return False
    if SMART_REQUIRE_CONFIRMED and not bank_data.get("confirmed", False):
        return False
    return True


def get_recorded_word(bank_data, global_index, trusted=None):
    """逐词判定：该位置若已收录、已确定且内容有效，返回 {"word","meaning"}，否则 None

    判定顺序：
      1) 精简总开关允许（trusted，不传则自动判断，见 is_word_skip_enabled）
      2) 该位置有词条、单词与释义都有效
      3) 该词已经「确定」：
           - 整本题库 confirmed=True        → 所有词都算已确定
           - 词条自带 confirmed=True        → 该词已确定
           - SMART_REQUIRE_CONFIRMED=False  → 只要收录了就当已确定
    """
    try:
        if trusted is None:
            trusted = is_word_skip_enabled(bank_data)
        if not trusted:
            return None
        w = get_word_from_bank(bank_data, global_index)
        if not w:
            return None
        word = (w.get("word") or "").strip()
        meaning = (w.get("meaning") or "").strip()
        if not word or not meaning:
            return None
        if word == "[识别失败]" or meaning == "[识别失败]":
            return None
        if SMART_REQUIRE_CONFIRMED and not is_word_confirmed(bank_data, w):
            return None
        return {"word": word, "meaning": meaning}
    except Exception:
        return None


def log_word_already_recorded(global_index, word, meaning, local_index=None, source=""):
    """统一输出「这个单词已收录」提示（含拼写与释义）

    学习阶段每碰到一个词，只要词典库里已经有它，就用这条统一格式打日志，
    不管是「已确认词典直接取用」还是「OCR识别后与库中记录一致」。
    """
    try:
        pos = f"本组第{local_index}词 / 词典第{global_index}词" if local_index else f"词典第{global_index}词"
        tail = f"  ［{source}］" if source else ""
        log.info(f"  [已收录] 这个单词已收录：{word} | {meaning}  【{pos}】{tail}")
    except Exception:
        pass


def try_migrate_default_bank(new_dict_name, monitor_input_func=None):
    """尝试将默认词汇表的题库迁移到新词典"""
    default_bank = load_dictionary_bank("默认词汇表")
    if not default_bank or len(default_bank.get("words", [])) == 0:
        return False
    
    word_count = len(default_bank["words"])
    
    log.info(f"[题库] 检测到旧题库 '默认词汇表' 有 {word_count} 词")
    
    prompt = f"检测到旧题库 '默认词汇表' 有 {word_count} 词，是否迁移到 '{new_dict_name}'？(y/n，默认y)"
    if monitor_input_func:
        ans = monitor_input_func(prompt, default="y")
    else:
        print()
        print("=" * 60)
        print(f"  📦 题库迁移检测")
        print("=" * 60)
        print(f"  旧题库: 默认词汇表 ({word_count} 词)")
        print(f"  新词典: {new_dict_name}")
        print("=" * 60)
        ans = input(f"\n  是否迁移旧题库到新词典？(y/n) [默认y]: ").strip().lower()
    
    if ans == "" or ans == "y":
        default_bank["dictionary_name"] = new_dict_name
        if save_dictionary_bank(new_dict_name, default_bank):
            old_path = get_bank_path("默认词汇表")
            try:
                old_path.unlink()
                log.info(f"[题库] 已删除旧题库文件")
            except:
                pass
            log.info(f"[题库] 已迁移 {word_count} 词到 '{new_dict_name}'")
            return True
        else:
            log.warning(f"[题库] 迁移失败")
            return False
    else:
        log.info(f"[题库] 用户选择不迁移")
        return False


# ================= 运行记录归档 & 词典导出（保存到「题库」文件夹） =================
# 说明：
#   1) 脚本每学完一组词，就把识别到的词记录进来
#   2) 运行中/结束时写入 题库/运行记录/运行记录_YYYY-MM-DD.json（按日期归档，同一天多次运行合并）
#   3) 同时把词典已收录的全部词导出成 题库/词典_<词典名>.json + .txt（词表+释义，人看的）
_run_record = {
    "started_at": None,
    "words": {},        # 本次运行记录到的词: {"词典索引": {"word":..,"meaning":..}}（统一用词典序号）
    "dict_name": None,
    "ranges": [],       # 本次运行实际学习过的词典索引区间 [(起, 止), ...]，用于精确归档
}


def _is_valid_word_entry(v):
    """判断一个词条是否是有效数据（过滤 [识别失败]、空词等脏数据）"""
    if not isinstance(v, dict):
        return False
    w = str(v.get("word", "") or "").strip()
    if not w or "识别失败" in w:
        return False
    return True


def _key_in_range(key, lo=None, hi=None):
    """判断索引键是否落在 [lo, hi] 区间内"""
    try:
        n = int(str(key))
    except Exception:
        return False
    if lo is not None and n < lo:
        return False
    if hi is not None and n > hi:
        return False
    return True


def run_record_note_range(lo, hi):
    """记录本次运行实际学习过的词典索引区间（学一组就登记一段）"""
    try:
        lo, hi = int(lo), int(hi)
    except Exception:
        return
    if hi < lo:
        return
    ranges = _run_record.setdefault("ranges", [])
    for r in ranges:
        if r[0] == lo and r[1] == hi:
            return
    ranges.append([lo, hi])


def _safe_filename(name):
    """把词典名处理成安全的文件名"""
    return re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip() or "未命名词典"


def run_record_start(dict_name):
    """开始记录本次运行（脚本启动时调用）"""
    _run_record["started_at"] = datetime.now()
    _run_record["words"] = {}
    _run_record["dict_name"] = dict_name
    _run_record["ranges"] = []


def run_record_collect(words, only_global=False, lo=None, hi=None):
    """把单词合并进本次运行记录
    支持两种格式：
      {"841": {"word": "x", "meaning": "y"}}        ← 本轮词表（键=词典序号）
      [{"index": 841, "word": "x", "meaning": "y"}] ← 题库词表

    only_global=True 时只接受「词典序号」这种整数键，并可用 lo/hi 限制区间；
    组内序号（1-30）会被丢弃，避免和词典序号串号。
    """
    if not words:
        return
    collected = _run_record["words"]
    try:
        if isinstance(words, dict):
            for k, v in words.items():
                if only_global and not _key_in_range(k):
                    continue
                if not _key_in_range(k, lo, hi):
                    continue
                if _is_valid_word_entry(v):
                    collected[str(k)] = {
                        "word": str(v.get("word", "")).strip(),
                        "meaning": str(v.get("meaning", "") or "").strip(),
                    }
        elif isinstance(words, list):
            for i, w in enumerate(words):
                if not _is_valid_word_entry(w):
                    continue
                key = str(w.get("index", i + 1))
                if only_global and not _key_in_range(key):
                    continue
                if not _key_in_range(key, lo, hi):
                    continue
                collected[key] = {
                    "word": str(w.get("word", "")).strip(),
                    "meaning": str(w.get("meaning", "") or "").strip(),
                }
    except Exception as e:
        log.debug(f"[归档] 合并单词失败: {e}")


def run_record_collect_from_progress():
    """兜底：把本次运行学到的词补捞进运行记录

    只从 progress.json 的 bank_dict（键=词典序号）里取，
    并且只取「本次运行已学区间」内的词，避免把上一次运行的旧词算进来。
    组内序号 word_dict（1-30）不参与归档，防止串号。
    """
    try:
        ranges = _run_record.get("ranges") or []
        if not ranges:
            return
        if not PROGRESS_PATH.exists():
            return
        with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        bank_dict = data.get("bank_dict", {}) or {}
        for r in ranges:
            run_record_collect(bank_dict, only_global=True, lo=r[0], hi=r[1])
    except Exception as e:
        log.debug(f"[归档] 从进度文件补捞失败: {e}")


def _run_record_path():
    return RUN_RECORD_DIR / f"运行记录_{datetime.now().strftime('%Y-%m-%d')}.json"


def run_record_save(stage=""):
    """把本次运行的单词记录按日期归档到 题库/运行记录/"""
    started = _run_record.get("started_at")
    path = _run_record_path()
    try:
        data = {}
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data.setdefault("date", datetime.now().strftime('%Y-%m-%d'))
        data["dictionary_name"] = _run_record.get("dict_name") or data.get("dictionary_name", "")

        new_words = dict(_run_record.get("words", {}))

        # 当天累计单词（同名索引去重，后记录的覆盖先记录的）
        day_words = data.get("words", {})
        for k, v in new_words.items():
            day_words[str(k)] = v
        data["words"] = day_words
        data["total_words"] = len(day_words)
        data["last_updated"] = now_str

        # 本次运行条目（同一次运行只保留一条，运行中不断更新）
        run_id = started.strftime('%Y-%m-%d %H:%M:%S') if started else now_str
        entry = None
        for r in data.get("runs", []):
            if r.get("run_id") == run_id:
                entry = r
                break
        if entry is None:
            entry = {"run_id": run_id, "start": run_id, "words": {}}
            data.setdefault("runs", []).append(entry)
        entry["end"] = now_str
        entry["stage"] = stage or entry.get("stage", "")
        entry_words = entry.get("words", {})
        entry_words.update(new_words)
        entry["words"] = entry_words
        entry["words_recorded"] = len(entry_words)
        try:
            entry["session_words_learned"] = stats.get("total_words_learned", 0) - _session_snapshot.get("total_words_learned", 0)
            entry["session_rounds"] = stats.get("total_rounds", 0) - _session_snapshot.get("total_rounds", 0)
        except Exception:
            pass
        data["runs"] = data.get("runs", [])[-300:]

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        range_txt = ""
        try:
            rs = _run_record.get("ranges") or []
            if rs:
                range_txt = "，覆盖词典第 " + "、".join(f"{a}-{b}" for a, b in rs) + " 词"
        except Exception:
            range_txt = ""
        log.info(f"[归档] 运行记录已保存: 题库\\运行记录\\{path.name} （本次 {entry['words_recorded']} 词 / 当天累计 {data['total_words']} 词{range_txt}）")
        return True
    except Exception as e:
        log.error(f"[归档] 运行记录保存失败: {e}")
        return False


def run_record_finish(stage="结束"):
    """结束归档（脚本停止时调用）"""
    run_record_collect_from_progress()
    run_record_save(stage)
    _run_record["started_at"] = None
    _run_record["words"] = {}


def export_dictionary_snapshot(dict_name, bank_data, reason=""):
    """把词典已收录的词导出成「词表+释义」文件，保存到「题库」文件夹
    产出两个文件：
      题库/词典_<词典名>.json  ← 程序读取用（结构化）
      题库/词典_<词典名>.txt   ← 人查看用（一行一个词+释义）
    """
    if not dict_name or not bank_data:
        return False
    try:
        words = list(bank_data.get("words", []))
        if not words:
            return False
        words.sort(key=lambda x: x.get("index", 0))
        safe = _safe_filename(dict_name)
        exported_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        payload = {
            "dictionary_name": dict_name,
            "total_words": len(words),
            "expected_total": bank_data.get("expected_total", len(words)),
            "confirmed": bank_data.get("confirmed", False),
            "exported_at": exported_at,
            "words": words,
        }
        json_path = BANK_DIR / f"词典_{safe}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        confirmed_cnt = count_confirmed_words({"words": words, "confirmed": payload["confirmed"]})

        txt_path = BANK_DIR / f"词典_{safe}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"# 词典：{dict_name}\n")
            f.write(f"# 已收录：{len(words)} 词（目标 {payload['expected_total']} 词）\n")
            f.write(f"# 已确定：{confirmed_cnt} 词（已确定的词以后刷到会跳过截图/OCR）\n")
            f.write(f"# 导出时间：{exported_at}" + (f"（{reason}）" if reason else "") + "\n")
            f.write("# 格式：序号. 单词  释义   [状态]\n")
            f.write("#" + "-" * 58 + "\n\n")
            for w in words:
                mark = "确定" if (payload["confirmed"] or w.get("confirmed")) else "待定"
                f.write(f"{w.get('index', '')}. {w.get('word', '')}  {w.get('meaning', '')}   [{mark}]\n")

        log.info(f"[导出] 词典已导出到题库文件夹: 词典_{safe}.json / 词典_{safe}.txt （{len(words)} 词，其中已确定 {confirmed_cnt} 词）")
        return True
    except Exception as e:
        log.error(f"[导出] 词典导出失败: {e}")
        return False


# ================= 坐标方案系统 =================
def apply_coord_profile(coord_config):
    """应用坐标方案到全局变量"""
    global LEARN, TEST, BTN_VIEW, BTN_EASY, BTN_CONTINUE_LEARN, LEARN_NEXT
    global REGION_WORD, REGION_MEAN, REGION_TODAY, REGION_WORD_INDEX, REGION_DICT_NAME
    global INPUT_SPELL, BTN_CONFIRM, TEST_NEXT, BTN_FINISH, BTN_BACK
    global BTN_TASK, BTN_AGAIN, OPT_COORDS, REGION_NUMBER, REGION_QUESTION_TYPE, REGION_OPTION
    
    LEARN = coord_config.get("learn", {})
    TEST = coord_config.get("test", {})
    
    BTN_VIEW = scale_point(LEARN.get("btn_view", [1675, 432]))
    BTN_EASY = scale_point(LEARN.get("btn_easy", [1846, 210]))
    BTN_CONTINUE_LEARN = scale_point(LEARN.get("btn_continue_learn", [1685, 945]))
    LEARN_NEXT = scale_point(LEARN.get("learn_next", [1679, 943]))
    REGION_WORD = scale_region(LEARN.get("word", [1467, 188, 1799, 290]))
    REGION_MEAN = scale_region(LEARN.get("meaning", [1480, 399, 1914, 596]))
    REGION_TODAY = scale_region(LEARN.get("today", [1632, 95, 1735, 160]))
    REGION_WORD_INDEX = scale_region(LEARN.get("word_index", [1294, 371, 1400, 410]))
    REGION_DICT_NAME = scale_region(LEARN.get("dict_name", [1480, 130, 1914, 180]))
    
    INPUT_SPELL = scale_point(TEST.get("input_spell", [1675, 378]))
    BTN_CONFIRM = scale_point(TEST.get("btn_confirm", [1680, 465]))
    TEST_NEXT = scale_point(TEST.get("test_next", [1679, 980]))
    BTN_FINISH = scale_point(TEST.get("btn_finish", [1670, 980]))
    BTN_BACK = scale_point(TEST.get("btn_back", [1470, 50]))
    BTN_TASK = scale_point(TEST.get("btn_task", [1055, 400]))
    BTN_AGAIN = scale_point(TEST.get("btn_again", [1800, 960]))
    OPT_COORDS = [scale_point(c) for c in TEST.get("option_coords", [[1680,420],[1680,500],[1680,580],[1680,650]])]
    REGION_NUMBER = scale_region(TEST.get("number", [1457, 99, 1616, 134]))
    REGION_QUESTION_TYPE = scale_region(TEST.get("question_type", [1463, 167, 1632, 200]))
    REGION_OPTION = [scale_region(r) for r in TEST.get("option_regions", [
        (1465,388,1895,440),(1465,468,1895,520),
        (1465,545,1895,597),(1465,619,1895,671),
    ])]


# ================= 日志系统 =================
_start_time = time.time()

def _get_elapsed_str():
    elapsed = int(time.time() - _start_time)
    h = elapsed // 3600
    m = (elapsed % 3600) // 60
    s = elapsed % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

class ElapsedFormatter(logging.Formatter):
    def format(self, record):
        if LOG_ELAPSED_PREFIX:
            record.elapsed = _get_elapsed_str()
            return super().format(record)
        return super().format(record)

def setup_logger():
    logger = logging.getLogger("brush")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    logger.propagate = False

    fmt = ElapsedFormatter(
        '[%(elapsed)s] [%(levelname)s] %(message)s' if LOG_ELAPSED_PREFIX
        else '[%(levelname)s] %(message)s'
    )

    if LOG_TO_CONSOLE:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    if LOG_TO_FILE:
        log_file = LOG_DIR / f"run_{datetime.now().strftime('%Y%m%d')}.log"
        fh = RotatingFileHandler(
            str(log_file), maxBytes=LOG_MAX_SIZE,
            backupCount=LOG_BACKUP_COUNT, encoding='utf-8'
        )
        fh.setFormatter(ElapsedFormatter(
            '%(asctime)s [%(elapsed)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(fh)

    return logger

log = setup_logger()
try:
    log.info(f"[坐标] 基准 {BASE_SCREEN_W}x{BASE_SCREEN_H}，当前 {SCREEN_W}x{SCREEN_H}，缩放 X={SCALE_X:.2f} Y={SCALE_Y:.2f}")
except Exception:
    pass


# ================= 全局状态 =================
stop_flag = False
pause_flag = False
calibration_mode = False  # 校准模式（第一组运行时开启）
calibration_changes = {}  # 校准过程中修改的坐标 {purpose: (x, y)}
calibration_renames = {}  # 校准过程中重命名的操作 {old_purpose: new_name}
pyautogui.FAILSAFE = False


# ================= 运行状态 =================
def load_monitor_state():
    """加载运行状态（不再包含监管模式）"""
    if MONITOR_STATE_FILE.exists():
        try:
            with open(MONITOR_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            return state
        except Exception as e:
            log.warning(f"[状态] 加载状态失败: {e}，已重置为默认状态")
            try:
                MONITOR_STATE_FILE.unlink()
            except:
                pass
    return {}

def save_monitor_state(status="运行中", round_num=1, words_learned=0, elapsed_seconds=0):
    """保存运行状态"""
    state = {}
    if MONITOR_STATE_FILE.exists():
        try:
            with open(MONITOR_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except:
            pass
    state["status"] = status
    state["round_num"] = round_num
    state["words_learned"] = words_learned
    state["elapsed_seconds"] = elapsed_seconds
    state["timestamp"] = datetime.now().isoformat()
    try:
        with open(MONITOR_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning(f"[状态] 保存状态失败: {e}")

def monitor_input(prompt, default="y"):
    """
    命令行输入：终端不可用时轮询文件
    返回用户输入，无输入时返回默认值
    """
    log.info(f"[输入] 等待用户输入: {prompt}")

    try:
        ans = input(f"  {prompt} (默认{default}): ").strip().lower()
        return ans if ans else default
    except EOFError:
        pass

    log.warning(f"[输入] 终端不可用，等待文件输入 (monitor_input.json)...")
    _last_mtime = 0
    if MONITOR_INPUT_FILE.exists():
        try:
            _last_mtime = os.path.getmtime(str(MONITOR_INPUT_FILE))
        except:
            _last_mtime = 0

    while not stop_flag:
        try:
            if MONITOR_INPUT_FILE.exists():
                mtime = os.path.getmtime(str(MONITOR_INPUT_FILE))
                if mtime > _last_mtime:
                    _last_mtime = mtime
                    try:
                        with open(MONITOR_INPUT_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        text = data.get("input", "").strip().lower()
                        if text:
                            log.info(f"[输入] 收到文件输入: {text}")
                            return text
                    except:
                        pass
        except:
            pass
        time.sleep(0.5)

    return default

def _supervised_read_input(prompt_hint=""):
    """
    校准模式下读取用户输入：
    1. 优先终端 input()
    2. 终端不可用时，轮询 MONITOR_INPUT_FILE
    返回用户输入字符串，全小写
    """
    global stop_flag

    try:
        hint = (prompt_hint or "").strip()
        if not hint:
            hint = "校准模式：按回车确认，或输入 q 终止脚本"
        ans = input(hint).strip().lower()
        return ans
    except EOFError:
        pass

    log.warning(f"[输入] 终端不可用，等待文件输入 (monitor_input.json)...")

    _last_mtime = 0
    if MONITOR_INPUT_FILE.exists():
        try:
            _last_mtime = os.path.getmtime(str(MONITOR_INPUT_FILE))
        except:
            _last_mtime = 0

    while not stop_flag:
        try:
            if MONITOR_INPUT_FILE.exists():
                mtime = os.path.getmtime(str(MONITOR_INPUT_FILE))
                if mtime > _last_mtime:
                    _last_mtime = mtime
                    try:
                        with open(MONITOR_INPUT_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        text = data.get("input", "").strip().lower()
                        if text:
                            log.info(f"[输入] 收到文件输入: {text}")
                            return text
                    except:
                        pass
        except:
            pass
        time.sleep(0.5)

    return "q"

def _calibrate_with_mouse(initial_x, initial_y):
    """用鼠标校准坐标：移动到目标位置，3秒后记录"""
    print()
    print(f"  🎯 鼠标校准模式")
    print(f"  当前坐标: ({initial_x}, {initial_y})")
    print(f"  请将鼠标移动到正确位置，3秒后自动记录...")
    try:
        import coordinate_profiles as cp
        x, y = cp.wait_and_capture("请将鼠标移动到目标位置，3秒后自动记录")
        print(f"  记录坐标: ({x}, {y})")
        confirm = input("  确认此坐标？(y=确认, r=重新选择) [默认y]: ").strip().lower()
        if confirm == "" or confirm == "y":
            return x, y
        else:
            return _calibrate_with_mouse(initial_x, initial_y)
    except Exception as e:
        print(f"  鼠标校准失败: {e}")
        return initial_x, initial_y

def supervised_click(x, y, purpose="点击操作", detail=None):
    """
    校准点击：只有第一组校准模式开启时，每步操作前等待用户确认
    返回值: True=执行成功, False=跳过, None=终止
    """
    global stop_flag, pause_flag, calibration_mode, calibration_changes, calibration_renames

    while pause_flag and not stop_flag:
        time.sleep(0.5)

    if stop_flag:
        return None

    display_purpose = calibration_renames.get(purpose, purpose)

    if DRY_RUN:
        log.info(f"[干跑] 本应点击 ({x}, {y}) - {display_purpose}")
        return True

    need_confirm = calibration_mode

    if need_confirm:
        log.info(f"[校准] 等待确认: 点击 ({x}, {y}) - {display_purpose}")
        print()
        if calibration_mode:
            print("=" * 60)
            print(f"  📐 [校准模式] 下一步操作")
            print("=" * 60)
            print(f"  操作类型: 点击")
            print(f"  操作名称: {display_purpose}")
            print(f"  目标坐标: ({x}, {y})")
            if detail:
                print(f"  详细说明: {detail}")
            print("=" * 60)
            print("  操作: Enter=确认执行, s=跳过, q=终止")
            print("        m x,y = 手动输入坐标, c = 鼠标选点校准")
            print("        n = 修改操作名称")
            print("=" * 60)
        else:
            print("=" * 50)
            print(f"  [校准] 下一步操作需要确认")
            print(f"  操作类型: 点击")
            print(f"  坐标: ({x}, {y})")
            print(f"  目的: {display_purpose}")
            print("=" * 50)
            print("  输入: Enter=确认, s=跳过, q=终止, m x,y=修改坐标, c=鼠标校准")

        while True:
            ans = _supervised_read_input(
                f"校准：执行「{display_purpose}」({x}, {y})？回车=确认，s=跳过，q=终止")

            if stop_flag:
                return None

            if ans == "" or ans == "y":
                log.info("[校准] 用户确认执行")
                break
            elif ans == "s":
                log.info("[校准] 用户跳过此步")
                return False
            elif ans == "q":
                log.info("[校准] 用户终止脚本")
                stop_flag = True
                return None
            elif ans == "n" and calibration_mode:
                new_name = input("  输入新的操作名称: ").strip()
                if new_name:
                    calibration_renames[purpose] = new_name
                    display_purpose = new_name
                    log.info(f"[校准] 操作已重命名: '{purpose}' → '{new_name}'")
                    print(f"  ✅ 已重命名为: {new_name}")
                    print()
                    print("=" * 60)
                    print(f"  📐 [校准模式] 下一步操作")
                    print("=" * 60)
                    print(f"  操作类型: 点击")
                    print(f"  操作名称: {display_purpose}")
                    print(f"  目标坐标: ({x}, {y})")
                    if detail:
                        print(f"  详细说明: {detail}")
                    print("=" * 60)
                    print("  操作: Enter=确认执行, s=跳过, q=终止")
                    print("        m x,y = 手动输入坐标, c = 鼠标选点校准")
                    print("        n = 修改操作名称")
                    print("=" * 60)
            elif ans.startswith("m") and "," in ans:
                try:
                    parts = ans[1:].replace(" ", "").split(",")
                    x, y = int(parts[0]), int(parts[1])
                    log.info(f"[校准] 用户修改坐标: ({x}, {y})")
                    if calibration_mode:
                        calibration_changes[purpose] = (x, y)
                    break
                except (ValueError, IndexError):
                    print("  格式错误，示例: m 100,200")
            elif ans == "c":
                x, y = _calibrate_with_mouse(x, y)
                log.info(f"[校准] 鼠标校准坐标: ({x}, {y})")
                if calibration_mode:
                    calibration_changes[purpose] = (x, y)
                break
            else:
                if calibration_mode:
                    print("  输入: Enter=确认, s=跳过, q=终止, m x,y=手动坐标, c=鼠标校准, n=重命名")
                else:
                    print("  输入: Enter=确认, s=跳过, q=终止, m x,y=修改坐标, c=鼠标校准")

    try:
        if MOUSE_CURVE:
            pyautogui.moveTo(x, y, duration=random.uniform(0.3, 0.8))
            time.sleep(random.uniform(0.1, 0.3))
        pyautogui.click(x, y)
        log.debug(f"[点击] ({x}, {y}) - {display_purpose}")
        return True
    except Exception as e:
        log.error(f"[点击] 执行失败: {e}")
        return False

def supervised_key(key, purpose="按键操作", detail=None):
    """
    校准按键：只有第一组校准模式开启时，每步操作前等待用户确认
    """
    global stop_flag, pause_flag, calibration_mode, calibration_renames

    while pause_flag and not stop_flag:
        time.sleep(0.5)

    if stop_flag:
        return None

    display_purpose = calibration_renames.get(purpose, purpose)

    if DRY_RUN:
        log.info(f"[干跑] 本应按键 '{key}' - {display_purpose}")
        return True

    need_confirm = calibration_mode

    if need_confirm:
        log.info(f"[校准] 等待确认: 按键 '{key}' - {display_purpose}")
        print()
        if calibration_mode:
            print("=" * 60)
            print(f"  📐 [校准模式] 下一步操作")
            print("=" * 60)
            print(f"  操作类型: 按键")
            print(f"  操作名称: {display_purpose}")
            print(f"  按键: {key}")
            if detail:
                print(f"  详细说明: {detail}")
            print("=" * 60)
            print("  操作: Enter=确认执行, s=跳过, q=终止")
            print("        n = 修改操作名称")
            print("=" * 60)
        else:
            print("=" * 50)
            print(f"  [校准] 下一步操作需要确认")
            print(f"  操作类型: 按键")
            print(f"  按键: {key}")
            print(f"  目的: {display_purpose}")
            print("=" * 50)
            print("  输入: Enter=确认, s=跳过, q=终止")

        while True:
            ans = _supervised_read_input(
                f"校准：按键「{key}」（{display_purpose}）？回车=确认，s=跳过，q=终止")

            if stop_flag:
                return None

            if ans == "" or ans == "y":
                log.info("[校准] 用户确认执行")
                break
            elif ans == "s":
                log.info("[校准] 用户跳过此步")
                return False
            elif ans == "q":
                log.info("[校准] 用户终止脚本")
                stop_flag = True
                return None
            elif ans == "n" and calibration_mode:
                new_name = input("  输入新的操作名称: ").strip()
                if new_name:
                    calibration_renames[purpose] = new_name
                    display_purpose = new_name
                    log.info(f"[校准] 操作已重命名: '{purpose}' → '{new_name}'")
                    print(f"  ✅ 已重命名为: {new_name}")
                    print()
                    print("=" * 60)
                    print(f"  📐 [校准模式] 下一步操作")
                    print("=" * 60)
                    print(f"  操作类型: 按键")
                    print(f"  操作名称: {display_purpose}")
                    print(f"  按键: {key}")
                    if detail:
                        print(f"  详细说明: {detail}")
                    print("=" * 60)
                    print("  操作: Enter=确认执行, s=跳过, q=终止")
                    print("        n = 修改操作名称")
                    print("=" * 60)
            else:
                if calibration_mode:
                    print("  输入: Enter=确认, s=跳过, q=终止, n=重命名")
                else:
                    print("  输入: Enter=确认, s=跳过, q=终止")

    try:
        keyboard.press_and_release(key)
        log.debug(f"[按键] '{key}' - {display_purpose}")
        return True
    except Exception as e:
        log.error(f"[按键] 执行失败: {e}")
        return False

def supervised_scroll(clicks, purpose="滚动操作"):
    """
    校准滚动：只有第一组校准模式开启时，每步操作前等待用户确认
    """
    global stop_flag, pause_flag

    while pause_flag and not stop_flag:
        time.sleep(0.5)

    if stop_flag:
        return None

    if DRY_RUN:
        log.info(f"[干跑] 本应滚动 {clicks} 格 - {purpose}")
        return True

    if calibration_mode:
        log.info(f"[校准] 等待确认: 滚动 {clicks} 格 - {purpose}")
        print()
        print("=" * 50)
        print(f"  [校准] 下一步操作需要确认")
        print(f"  操作类型: 滚动")
        print(f"  滚动量: {clicks} 格")
        print(f"  目的: {purpose}")
        print("=" * 50)
        print("  输入: Enter=确认, s=跳过, q=终止")

        while True:
            ans = _supervised_read_input(
                f"校准：滚动 {clicks} 格（{purpose}）？回车=确认，s=跳过，q=终止")

            if stop_flag:
                return None

            if ans == "" or ans == "y":
                log.info("[校准] 用户确认执行")
                break
            elif ans == "s":
                log.info("[校准] 用户跳过此步")
                return False
            elif ans == "q":
                log.info("[校准] 用户终止脚本")
                stop_flag = True
                return None
            else:
                print("  输入: Enter=确认, s=跳过, q=终止")

    try:
        pyautogui.scroll(clicks)
        log.debug(f"[滚动] {clicks} 格 - {purpose}")
        return True
    except Exception as e:
        log.error(f"[滚动] 执行失败: {e}")
        return False


stats = {
    "total_rounds": 0,
    "total_words_learned": 0,
    "total_questions_answered": 0,
    "total_correct_answers": 0,
    "total_wrong_answers": 0,
    "intentional_wrong": 0,
    "total_runtime_seconds": 0,
    "start_time": None,
    "last_update": None,
}


# ================= 统计管理 =================
def load_stats():
    global stats
    if STATS_PATH.exists():
        try:
            with open(STATS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                stats.update(data)
            log.info(f"[统计] 已加载历史统计：共{stats['total_rounds']}组，{stats['total_words_learned']}词")
        except Exception as e:
            log.warning(f"[统计] 加载统计文件失败: {e}")

_session_snapshot = {}  # 本次运行前的统计快照，用于区分本次 vs 累计

def save_stats():
    try:
        stats["last_update"] = datetime.now().isoformat()
        # 正确累加运行时间：上次累计 + 本次运行时间（防止多次调用导致重复累加）
        session_runtime = int(time.time() - _start_time)
        stats["total_runtime_seconds"] = _session_snapshot.get("total_runtime_seconds", 0) + session_runtime
        with open(STATS_PATH, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        log.debug("[统计] 已保存统计数据")
    except Exception as e:
        log.error(f"[统计] 保存统计失败: {e}")

def print_stats_summary():
    runtime = int(time.time() - _start_time)
    h, m, s = runtime // 3600, (runtime % 3600) // 60, runtime % 60
    total_q = stats["total_questions_answered"]
    acc = (stats["total_correct_answers"] / total_q * 100) if total_q > 0 else 0

    # 计算本次运行的数据（当前累计 - 本次运行前的快照）
    session_words = stats.get("total_words_learned", 0) - _session_snapshot.get("total_words_learned", 0)
    session_rounds = stats.get("total_rounds", 0) - _session_snapshot.get("total_rounds", 0)
    session_q = total_q - _session_snapshot.get("total_questions_answered", 0)

    log.info("=" * 50)
    log.info("  运行统计")
    log.info("=" * 50)
    log.info(f"  本次运行时间: {h:02d}:{m:02d}:{s:02d}")
    log.info(f"  本次完成组数: {session_rounds}  (累计: {stats['total_rounds']})")
    log.info(f"  本次学习单词: {session_words}  (累计: {stats['total_words_learned']})")
    log.info(f"  本次答题数: {session_q}  (累计: {total_q})")
    log.info(f"  正确数: {stats['total_correct_answers']}")
    log.info(f"  错误数: {stats['total_wrong_answers']}")
    log.info(f"  故意答错: {stats['intentional_wrong']}")
    log.info(f"  正确率: {acc:.1f}%")
    log.info("=" * 50)


# ================= 进度管理（断点续传） =================
progress_data = {}

def save_progress(round_num, phase, **kwargs):
    """保存进度到 progress.json。
    当新保存缺少详细字段（learn_local_index等）但旧进度有且阶段相同时，
    自动保留旧详细字段，防止异常处理用基本信息覆盖学习/测试函数保存的详细进度。
    """
    global progress_data
    detailed_keys = ('learn_local_index', 'learn_global_index', 'word_dict', 'bank_dict',
                     'test_completed', 'test_current_qn')
    if not any(k in kwargs for k in detailed_keys) and progress_data and progress_data.get("phase") == phase:
        for k in detailed_keys:
            if k in progress_data and k not in kwargs:
                kwargs[k] = progress_data[k]

    progress_data = {
        "round_num": round_num,
        "phase": phase,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": int(time.time() - _start_time),
    }
    progress_data.update(kwargs)
    try:
        with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, indent=2, ensure_ascii=False)
        log.debug(f"[进度] 已保存：第{round_num}组，阶段={phase}")
    except Exception as e:
        log.error(f"[进度] 保存失败: {e}")

def load_progress():
    global progress_data
    if PROGRESS_PATH.exists():
        try:
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            progress_data = data  # 同步到全局变量，使 save_progress 能保留已有详细字段
            log.info(f"[进度] 检测到上次进度：第{data.get('round_num', '?')}组，阶段={data.get('phase', '?')}")
            return data
        except Exception as e:
            log.warning(f"[进度] 读取失败: {e}")
    return None

def clear_progress():
    global progress_data
    progress_data = {}
    if PROGRESS_PATH.exists():
        try:
            PROGRESS_PATH.unlink()
            log.info("[进度] 已清除进度文件（将通过OCR重建起始位置）")
        except Exception as e:
            log.warning(f"[进度] 清除失败: {e}")

def ask_resume_progress(prog, ocr_info=None):
    if not prog:
        return False, None
    round_num = prog.get("round_num", 1)
    phase = prog.get("phase", "unknown")
    ts = prog.get("timestamp", "unknown")

    # 进度校验：如果 OCR 从 App 推算的组号，和进度文件里的组号差距太大，
    # 说明进度文件已经过期（比如 App 已经重新开始一轮），不再恢复旧进度。
    if ocr_info:
        try:
            # App 明确显示「0/总数」= 全新一轮，不恢复旧进度
            if ocr_info.get("app_progress_read") and int(ocr_info.get("ocr_global_done", 0) or 0) == 0:
                log.warning("[进度] App 明确显示进度为 0，判定为新的一轮，不恢复旧进度")
                print()
                print("=" * 50)
                print("  [进度校验] App 显示进度是 0，说明是新的一轮")
                print("  自动使用新进度（不恢复旧进度文件）")
                print("=" * 50)
                return False, prog
            ocr_round = int(ocr_info.get("ocr_round", 0) or 0)
            if ocr_round > 0 and abs(ocr_round - int(round_num)) > 2:
                log.warning(
                    f"[进度] App 推算第 {ocr_round} 组，进度文件是第 {round_num} 组，差距过大，不恢复旧进度"
                )
                print()
                print("=" * 50)
                print(f"  [进度校验] App 显示第 {ocr_round} 组，进度文件是第 {round_num} 组")
                print("  两边对不上，自动使用 App 的进度（不恢复旧进度文件）")
                print("=" * 50)
                return False, prog
        except Exception:
            pass
    print()
    print("=" * 50)
    print(f"  [进度文件] 第 {round_num} 组 / {phase}")
    print(f"  保存时间：{ts}")
    if ocr_info and ocr_info.get('page_type') in ['learning', 'testing']:
        print("-" * 50)
        print(f"  [OCR实时检测]")
        print(f"  页面类型：{ocr_info.get('page_type', '未知')}")
        if ocr_info.get('progress_text'):
            print(f"  进度区域：{ocr_info['progress_text']}")
        if ocr_info.get('today_text'):
            print(f"  今日新词：{ocr_info['today_text']}")
        if ocr_info.get('learn_global', 0) > 0:
            print(f"  推算位置：第{ocr_info['ocr_round']}组 第{ocr_info['learn_local']}词 / 词典第{ocr_info['learn_global']}词")
    print("=" * 50)
    ans = monitor_input("是否从上次进度继续？(y/n，默认y)", default="y").strip().lower()
    return ans in ('', 'y', 'yes'), prog


# ================= 热键监听 =================
def toggle_pause():
    global pause_flag
    pause_flag = not pause_flag
    if pause_flag:
        log.info("[暂停] 脚本已暂停，按空格键继续...")
        save_stats()
    else:
        log.info("[继续] 脚本恢复运行")

def on_escape():
    global stop_flag
    log.warning("[停止] 收到停止信号，正在保存进度...")
    stop_flag = True
    save_stats()

def on_save_progress():
    log.info("[热键] 手动保存进度")
    save_stats()

def auto_recover(reason="未知异常", phase="current", attempts=3):
    """
    替代原来的监管模式：出错后自动重试识别页面并尝试导航。
    返回 True = 已恢复，可以继续；False = 恢复失败，调用方应停止脚本。
    phase: learning / testing / startup / current
    """
    global stop_flag

    if stop_flag:
        return False

    log.warning(f"[自动恢复] 遇到问题：{reason}（阶段：{phase}）")

    for i in range(1, attempts + 1):
        if stop_flag:
            return False

        _sleep(1.5)
        try:
            page = detect_current_page()
        except Exception as e:
            log.warning(f"[自动恢复] 第{i}/{attempts}次检测失败: {e}")
            continue

        log.info(f"[自动恢复] 第{i}/{attempts}次检测：当前页面={page}")

        try:
            if phase == "testing":
                if page == "testing":
                    log.info("[自动恢复] ✓ 已在测试页面，继续运行")
                    return True
                if navigate_to_page("testing", max_attempts=2):
                    log.info("[自动恢复] ✓ 已回到测试页面")
                    return True
            elif phase == "learning":
                if page == "learning":
                    log.info("[自动恢复] ✓ 已在学习页面，继续运行")
                    return True
                if safe_navigate_to_learn():
                    log.info("[自动恢复] ✓ 已回到学习页面")
                    return True
            elif phase == "startup":
                if page in ("learning", "testing"):
                    log.info(f"[自动恢复] ✓ 已识别页面: {page}")
                    return True
                if navigate_to_page("testing", max_attempts=2):
                    log.info("[自动恢复] ✓ 已导航到测试页面")
                    return True
                if safe_navigate_to_learn():
                    log.info("[自动恢复] ✓ 已导航到学习页面")
                    return True
            else:
                if page in ("learning", "testing"):
                    log.info(f"[自动恢复] ✓ 页面已恢复: {page}")
                    return True
        except Exception as e:
            log.warning(f"[自动恢复] 第{i}/{attempts}次导航出错: {e}")

    log.error(f"[自动恢复] 尝试 {attempts} 轮仍失败，脚本停止。")
    log.error("[自动恢复] 请检查：1.App 页面是否正常  2.坐标方案是否匹配  3.认字引擎是否在运行")
    return False


def start_hotkey_listeners():
    def _stop_listener():
        keyboard.wait(HK_STOP)
        on_escape()
    threading.Thread(target=_stop_listener, daemon=True).start()
    keyboard.add_hotkey(HK_PAUSE, toggle_pause)
    keyboard.add_hotkey(HK_SAVE, on_save_progress)

    log.info(f"[热键] 停止={HK_STOP.upper()}，暂停={HK_PAUSE.upper()}，保存进度={HK_SAVE.upper()}")


# ================= 工具函数 =================
def _wait_if_paused():
    """暂停时阻塞在这里，直到继续或停止。"""
    while pause_flag and not stop_flag:
        time.sleep(0.2)

def _sleep(seconds):
    interval = 0.1
    elapsed = 0
    while elapsed < seconds:
        if stop_flag:
            return
        _wait_if_paused()
        if stop_flag:
            return
        time.sleep(min(interval, seconds - elapsed))
        elapsed += interval

def set_english_input():
    """
    把输入法切成英文，并且只对「你正在操作的那个窗口」（OneClass）生效。

    老写法只调 ActivateKeyboardLayout，那个函数改的是脚本自己这个进程，
    对 OneClass 那个窗口不起作用——所以界面上看到的输入法其实一直没变，
    拼写题就容易打出中文。
    现在改成：先给前台窗口发一条「请换成英文」的系统消息，
    发不进去再退回到「把脚本挂到那个窗口上再切」的老办法。
    """
    if DRY_RUN:
        log.debug("[干跑] 跳过输入法切换")
        return True
    try:
        user32 = ctypes.windll.user32
        HKL_EN = 0x04090409                      # 英文（美国）键盘布局
        WM_INPUTLANGCHANGEREQUEST = 0x0050       # 「请换输入法」这条系统消息的编号

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            log.warning("[输入法] 取不到当前窗口，跳过切换")
            return False

        if user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, HKL_EN):
            log.debug(f"[输入法] 已让前台窗口切到英文 (hwnd={hwnd})")
            return True

        # 消息发不进去时：把脚本的输入线程挂到那个窗口上，再切一次
        try:
            pid = ctypes.c_ulong()
            tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            my_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            attached = user32.AttachThreadInput(my_tid, tid, True)
            try:
                if user32.ActivateKeyboardLayout(HKL_EN, 0x0100):
                    log.debug(f"[输入法] 已通过挂线程方式切到英文 (hwnd={hwnd})")
                    return True
            finally:
                if attached:
                    user32.AttachThreadInput(my_tid, tid, False)
        except Exception as e2:
            log.debug(f"[输入法] 挂线程切换异常: {e2}")

        log.warning(f"[输入法] 切英文失败 (hwnd={hwnd})，可能没装英文键盘，拼写题可能打出中文")
        return False
    except Exception as e:
        log.debug(f"[输入法] 切换异常: {e}")
        return False

def _ease_out(t):
    return 1 - (1 - t) ** 2

def curve_move_to(x, y, duration=None):
    if DRY_RUN:
        return
    if not MOUSE_CURVE:
        pyautogui.moveTo(x, y, duration=duration or 0.1)
        return
    start_x, start_y = pyautogui.position()
    dx = x - start_x
    dy = y - start_y
    dist = (dx**2 + dy**2) ** 0.5
    if duration is None:
        duration = max(0.05, min(0.3, dist / 2000))
    steps = max(5, int(duration * 60))
    ctrl_x = start_x + dx * 0.5 + random.uniform(-min(100, dist*0.3), min(100, dist*0.3))
    ctrl_y = start_y + dy * 0.5 + random.uniform(-min(60, dist*0.2), min(60, dist*0.2))
    for i in range(steps + 1):
        if stop_flag:
            return
        t = i / steps
        et = _ease_out(t)
        cx = (1-et)**2 * start_x + 2*(1-et)*et * ctrl_x + et**2 * x
        cy = (1-et)**2 * start_y + 2*(1-et)*et * ctrl_y + et**2 * y
        pyautogui.moveTo(int(cx), int(cy))
        time.sleep(duration / steps)

def click(coord, delay=0.5, purpose="点击操作"):
    jx = coord[0] + random.randint(-3, 3)
    jy = coord[1] + random.randint(-3, 3)

    # 统一走点击封装（校准模式下会询问确认）
    result = supervised_click(jx, jy, purpose=purpose)
    if result is None:
        return False
    if result is False:
        return False

    actual_delay = delay + random.uniform(-0.1, 0.2) if delay < 1 else delay + random.uniform(-0.3, 0.5)
    _sleep(max(0.1, actual_delay))
    return True

def _type_word(word):
    if DRY_RUN:
        log.info(f"[干跑] 本应输入: {word}")
        return
    log.debug(f"[打字] 输入: {word}")
    for ch in word:
        if stop_flag:
            return
        while pause_flag:
            time.sleep(0.3)
            if stop_flag:
                return
        pyautogui.typewrite(ch, interval=random.uniform(0.04, 0.18))
        if random.random() < 0.05:
            time.sleep(random.uniform(0.1, 0.3))
    time.sleep(random.uniform(0.1, 0.3))

def _move_away():
    if DRY_RUN:
        return
    pyautogui.moveTo(*BTN_EASY)

def format_td(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ================= 反检测模拟函数 =================
def human_delay(min_sec=None, max_sec=None):
    if DRY_RUN:
        return 0.0
    if min_sec is None:
        min_sec, max_sec = OP_DELAY_RANGE[0], OP_DELAY_RANGE[1]
    delay = random.uniform(min_sec, max_sec)
    _sleep(delay)
    return delay

def human_read():
    if DRY_RUN:
        return
    read_time = random.uniform(*READ_TIME_RANGE)
    log.debug(f"[阅读] 思考 {read_time:.1f} 秒")
    _sleep(read_time)
    return read_time

def should_fail(question_num, total_questions=None):
    if total_questions is None:
        total_questions = GROUP_SIZE
    if question_num <= 3 or question_num >= total_questions - 2:
        return False
    if random.random() < FAIL_RATE:
        return True
    return False

def human_hesitate():
    if random.random() < HESITATE_RATE:
        # 只把鼠标移到某个选项上停顿一下，绝不点击。
        # 这个 App 点一下就提交，点错选项等于真的答错，会拉低正确率。
        log.debug("[犹豫] 模拟犹豫：鼠标移到选项上停顿")
        try:
            hx, hy = OPT_COORDS[random.randint(0, len(OPT_COORDS)-1)]
            curve_move_to(hx, hy)
        except Exception:
            pass
        _sleep(random.uniform(0.6, 1.2))
        return True
    return False

def human_review():
    if random.random() < REVIEW_RATE:
        log.debug("[检查] 模拟答题后检查")
        _sleep(random.uniform(0.5, 1.0))
        curve_move_to(
            random.randint(1500, 1800),
            random.randint(400, 600),
            duration=random.uniform(0.3, 0.8)
        )
        return True
    return False

def random_break(question_count_in_phase):
    if not RANDOM_BREAK_ENABLED:
        return False
    interval = random.randint(BREAK_INTERVAL_MIN, BREAK_INTERVAL_MAX)
    if question_count_in_phase > 0 and question_count_in_phase % interval == 0:
        break_time = random.uniform(BREAK_MIN, BREAK_MAX)
        log.info(f"[休息] 随机休息 {break_time:.0f} 秒（模拟走神/喝水）")
        _sleep(break_time)
        return True
    return False

def rest_between_rounds():
    if not REST_ENABLED:
        return
    rest_time = random.uniform(REST_MIN, REST_MAX)
    log.info(f"[休息] 本组结束，休息 {rest_time:.0f} 秒 ({rest_time/60:.1f}分钟)")
    _sleep(rest_time)


# ================= Umi-OCR =================
_ocr_consecutive_fail = [0]  # OCR 连续整批失败次数（用于退避，避免连环失败时疯狂重试）
_ocr_in_recovery = [False]  # OCR恢复中标志（防止递归检测）
_page_mismatch = [False]   # 页面跳变标志：学习时发现页面已变，通知主循环退出
# OCR恢复阶段已经判断出的页面类型（类型, 时间戳）；外层页面检测读不到字时直接采用它
_ocr_recovered_page = [None, 0.0]

def _ocr_umi(image_source):
    if isinstance(image_source, tuple):
        img = ImageGrab.grab(bbox=image_source)
        # 选项行等小区域文字很小，先放大 2 倍再识别，中文准确率明显更高
        if img.width <= 700 and img.height <= 140:
            _resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize((img.width * 2, img.height * 2), _resample)
    else:
        img = Image.open(image_source)
        if img.mode != 'RGB':
            img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    # 连续失败退避：OCR 服务可能暂时卡住，稍等片刻再发请求，避免雪崩式失败
    # 最大重试上限：连续失败超过3次，重新检测页面状态（学习/测试）自动恢复
    # 熔断：连续失败太多次，直接停止脚本，避免死循环把 OCR 服务打崩
    if _ocr_consecutive_fail[0] >= 8:
        global stop_flag
        log.error(f"[OCR] 连续失败 {_ocr_consecutive_fail[0]} 次，触发熔断，停止脚本")
        print()
        print("=" * 60)
        print("  [!] OCR 连续失败太多次，脚本已自动停止")
        print("  请检查：")
        print("    1. App 页面是否正常（是否停在测试/学习页）")
        print("    2. 认字引擎是否还在运行")
        print("    3. 坐标方案是否匹配当前屏幕")
        print("=" * 60)
        stop_flag = True
        return ""

    if _ocr_consecutive_fail[0] >= 2 and not _ocr_in_recovery[0]:
        # 恢复逻辑不再限制主线程：测试阶段的 OCR 在 worker 线程里跑，
        # 如果只在主线程恢复，worker 线程会永远跳过恢复。
        _ocr_consecutive_fail[0] = 0
        _ocr_in_recovery[0] = True
        try:
            log.warning("[OCR] 连续失败超过2次，重新检测页面状态...")
            page_type = detect_current_page()
            log.info(f"[OCR恢复] 检测到页面类型: {page_type}")
            if page_type in ("learning", "testing", "task_list"):
                # 把恢复结果留给外层 detect_current_page 使用，避免它读不到字又判 unknown
                _ocr_recovered_page[0] = page_type
                _ocr_recovered_page[1] = time.time()
            if page_type == "learning":
                log.info("[OCR恢复] 当前是学习页面，继续学习阶段")
            elif page_type == "testing":
                log.warning("[OCR恢复] 当前是测试页面，说明 App 已切到测试阶段")
                _page_mismatch[0] = True
            elif page_type == "task_list":
                log.info("[OCR恢复] 当前是任务列表页面")
            else:
                log.warning(f"[OCR恢复] 页面类型未知({page_type})，继续重试OCR（连续失败8次会自动停止）")
        finally:
            _ocr_in_recovery[0] = False
    elif _ocr_consecutive_fail[0] == 1 and not _ocr_in_recovery[0]:
        backoff = min(2.0 * _ocr_consecutive_fail[0], 6.0)
        log.debug(f"[OCR] 连续{_ocr_consecutive_fail[0]}批失败，退避 {backoff:.0f} 秒...")
        _sleep(backoff)

    last_error = None
    for attempt in range(1, UMI_OCR_RETRY + 1):
        _wait_if_paused()
        if stop_flag:
            return ""
        try:
            req = urllib.request.Request(UMI_OCR_URL,
                data=json.dumps({"base64": b64}).encode(),
                method="POST", headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=UMI_OCR_TIMEOUT).read())
            if resp.get("code") == 100:
                data = resp.get("data", "")
                if isinstance(data, list):
                    _ocr_consecutive_fail[0] = 0
                    return "".join(item.get("text", "") for item in data).strip()
                _ocr_consecutive_fail[0] = 0
                return data.strip() if isinstance(data, str) else ""
            last_error = f"code={resp.get('code')}"
        except Exception as e:
            last_error = str(e)
        if attempt < UMI_OCR_RETRY:
            log.debug(f"[OCR] 第{attempt}次失败: {last_error}，{UMI_OCR_RETRY_DELAY}秒后重试...")
            time.sleep(UMI_OCR_RETRY_DELAY)
    _ocr_consecutive_fail[0] += 1
    log.warning(f"[OCR] 全部{UMI_OCR_RETRY}次失败: {last_error}")
    return ""

def ocr_file(image_path):
    result = _ocr_umi(image_path)
    log.debug(f"[OCR] 文件 {Path(image_path).name}: '{result[:50]}...'")
    return result

def ocr_region(region):
    _wait_if_paused()
    if stop_flag:
        return ""
    result = _ocr_umi(region)
    log.debug(f"[OCR] 区域 {region}: '{result[:50]}...'")
    return result

def ocr_word_index():
    t = ocr_region(REGION_WORD_INDEX)
    return t.strip() if re.search(r'\d+\s*/\s*\d+', t) else None

def wait_page_loaded(timeout=5, region=None):
    """检测页面是否加载完成（检测单词区域是否有内容）
    用于精简学习模式，避免页面没加载完就点击
    """
    if region is None:
        region = REGION_WORD
    for _ in range(timeout * 10):
        text = ocr_region(region)
        if text and len(text.strip()) > 1:
            return True
        time.sleep(0.1)
    return False

def init_umi():
    for attempt in range(3):
        try:
            req = urllib.request.Request(UMI_OCR_URL, method="POST")
            req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(req, timeout=3)
            log.info("[OCR] ✓ Umi-OCR 已连接")
            return True
        except Exception as e:
            log.warning(f"[OCR] 连接失败(尝试{attempt+1}/3): {e}")
            time.sleep(1)
    log.error("[OCR] Umi-OCR 无法连接，请确认已启动")
    return False


# ================= 全屏 OCR 定位辅助 =================
def ocr_full_screen(image_source=None):
    """
    全屏OCR，返回识别到的所有文字块及其坐标
    参数:
        image_source: 图片路径/区域元组/None(全屏截图)
    返回:
        [{"text": "...", "x": cx, "y": cy, "box": [...]}, ...]
    """
    _wait_if_paused()
    if stop_flag:
        return []
    if image_source is None:
        img = ImageGrab.grab()
    elif isinstance(image_source, tuple):
        img = ImageGrab.grab(bbox=image_source)
    elif isinstance(image_source, str):
        img = Image.open(image_source)
    else:
        img = image_source

    if img.mode != 'RGB':
        img = img.convert('RGB')

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        req = urllib.request.Request(UMI_OCR_URL,
            data=json.dumps({"base64": b64}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=UMI_OCR_TIMEOUT).read())

        blocks = []
        if resp.get("code") == 100:
            data = resp.get("data", [])
            if isinstance(data, list):
                for item in data:
                    text = item.get("text", "").strip()
                    box = item.get("box", [])

                    if text and box:
                        try:
                            # box格式: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 四角坐标
                            if isinstance(box[0], list) and len(box) >= 4:
                                x_coords = [p[0] for p in box]
                                y_coords = [p[1] for p in box]
                                cx = sum(x_coords) // len(x_coords)
                                cy = sum(y_coords) // len(y_coords)
                            # 备选: 扁平格式 [x_min, y_min, x_max, y_max]
                            elif len(box) >= 4 and isinstance(box[0], (int, float)):
                                cx = (box[0] + box[2]) // 2
                                cy = (box[1] + box[3]) // 2
                            else:
                                continue

                            blocks.append({
                                "text": text,
                                "x": int(cx),
                                "y": int(cy),
                                "box": box
                            })
                        except Exception:
                            continue

        log.debug(f"[OCR全屏] 识别到 {len(blocks)} 个文字块")
        return blocks

    except Exception as e:
        log.warning(f"[OCR全屏] 调用失败: {e}")
        return []


def find_text_position(blocks, keyword):
    """
    在OCR结果中搜索关键词，返回第一个匹配的中心坐标
    参数:
        blocks: ocr_full_screen()返回的文字块列表
        keyword: 要搜索的关键词
    返回:
        (x, y, matched_text) 或 None
    """
    matches = find_all_text_positions(blocks, keyword)
    return matches[0] if matches else None


def find_all_text_positions(blocks, keyword):
    """
    在OCR结果中搜索关键词，返回所有匹配项
    参数:
        blocks: ocr_full_screen()返回的文字块列表
        keyword: 要搜索的关键词
    返回:
        [(x, y, matched_text), ...] 或空列表
    """
    keyword_lower = keyword.lower().strip()
    matches = []
    for block in blocks:
        text = block.get("text", "").strip()
        if keyword_lower in text.lower():
            matches.append((block["x"], block["y"], text))
    return matches


# ================= 智能导航 =================
def navigate_to_page(target_page="testing", max_attempts=5):
    """
    导航到指定页面，失败时返回 False（由自动恢复决定是否停止）
    target_page: 'learning' / 'testing' / 'task_list'
    """
    page_names = {
        "learning": "单词学习页面",
        "testing": "单词测试页面",
        "task_list": "任务列表页面"
    }
    target_name = page_names.get(target_page, target_page)
    log.info(f"[导航] 开始导航到{target_name}...")

    for attempt in range(max_attempts):
        if stop_flag:
            return False

        current_page = detect_current_page()
        log.info(f"[导航] 第{attempt+1}步，当前页面: {current_page}")

        if current_page == target_page:
            log.info(f"[导航] ✓ 已到达{target_name}")
            return True

        # 根据当前页面类型尝试自动导航
        if current_page == "task_list":
            log.info("[导航] 当前在任务列表页，尝试点击'再来一组'")
            supervised_click(BTN_AGAIN[0], BTN_AGAIN[1], purpose="点击'再来一组'")
            _sleep(10)
            continue
        elif current_page == "testing" and target_page == "learning":
            log.info("[导航] 当前在测试页面，需要返回到学习页面")
            supervised_click(BTN_BACK[0], BTN_BACK[1], purpose="点击返回按钮")
            _sleep(3)
            continue
        elif current_page == "learning" and target_page == "testing":
            log.info("[导航] 当前在学习页面，需要进入测试页面")
            _sleep(3)
            supervised_click(BTN_CONTINUE_LEARN[0], BTN_CONTINUE_LEARN[1], purpose="点击继续背单词")
            if attempt == 0:
                _sleep(15)
            else:
                _sleep(5)
            continue
        elif current_page == "unknown" and target_page == "testing":
            log.info("[导航] 当前页面未知，尝试进入测试页面")
            if attempt < 2:
                _sleep(3)
                supervised_click(BTN_CONTINUE_LEARN[0], BTN_CONTINUE_LEARN[1], purpose="点击继续背单词")
                _sleep(10)
            else:
                supervised_click(BTN_BACK[0], BTN_BACK[1], purpose="点击返回按钮")
                _sleep(3)
                supervised_click(BTN_TASK[0], BTN_TASK[1], purpose="点击任务按钮")
                _sleep(5)
                supervised_click(BTN_AGAIN[0], BTN_AGAIN[1], purpose="点击再来一组")
                _sleep(15)
            continue

        # 自动导航失败：记录日志，继续下一轮尝试
        log.warning(f"[导航] 无法自动从'{current_page}'导航到'{target_name}'（第{attempt+1}次）")
        _sleep(2)

    log.error(f"[导航] 尝试 {max_attempts} 次后仍未到达{target_name}")
    return False


def navigate_to_test(max_attempts=10):
    """导航到测试页面（兼容旧函数名）"""
    return navigate_to_page("testing", max_attempts)


def navigate_to_learn(max_attempts=10):
    """导航到学习页面"""
    return navigate_to_page("learning", max_attempts)


# ================= 阶段1：学习 =================
def _restart_learn_flow(max_retries=2):
    """
    重启学习流程，返回页面恢复状态
    返回值:
        True - 学习页面恢复成功
        "testing" - 当前已是测试页面
        "result" - 当前是结果页面
        "task_list" - 当前是任务列表页
        False - 页面恢复失败
    """
    log.warning("[重启] 页面卡住，开始用固定坐标重试导航...")
    
    for attempt in range(1, max_retries + 1):
        log.warning(f"[重启] 使用固定坐标重试(第{attempt}/{max_retries}次)...")
        click(BTN_BACK, 1)
        click(BTN_TASK, 5)
        click(BTN_AGAIN, 0.5)
        _sleep(15)
        
        page_status = ensure_page_loaded(max_retries=1)
        if page_status:
            log.info(f"[重启] 页面恢复成功: {page_status}")
            return page_status
        log.warning(f"[重启] 第{attempt}次尝试失败，继续重试...")
    
    log.error("[重启] 所有重试均失败，页面未能恢复")
    return False

def is_english(text):
    if not text:
        return False
    en = cn = 0
    for c in text:
        if '一' <= c <= '鿿':
            cn += 1
        elif c.isalpha() or c.isdigit():
            en += 1
    return en > cn

def clean_text(text):
    if not text:
        return ""
    text = text.replace('\n', ' ')
    text = re.sub(r'([一-鿿])\s+([一-鿿])', r'\1\2', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s*([,;:.])\s*', r'\1', text)
    return text.strip()

def classify(text):
    if not text:
        return "", ""
    text = clean_text(text)
    return (text, "") if is_english(text) else ("", text)

def ensure_page_loaded(max_retries=3):
    """
    确保学习页面已加载
    返回值:
        True - 学习页面加载成功
        "testing" - 当前已经是测试页面，应跳过学习直接进入测试
        "result" - 当前是结果页面（已完成一轮），应进入下一轮或结束
        "task_list" - 当前是任务列表页，需要点击进入词典
        False - 页面加载失败
    """
    for attempt in range(1, max_retries + 1):
        text = ocr_region(REGION_TODAY)
        if re.search(r'\d+\s*/\s*\d+', text):
            log.info(f"[页面] 加载成功：'{text}'")
            return True

        log.warning(f"[页面] 加载失败(尝试{attempt}/{max_retries})，重试...")


        _restart_learn_flow()
        if stop_flag:
            return False
    return False


def is_learning_complete(text):
    """检测是否为学习完成过渡页面"""
    if not text:
        return False
    keywords = ["学习完成", "跳转到", "单词测试", "确认", "秒后", "倒计时", "完成"]
    count = sum(1 for kw in keywords if kw in text)
    return count >= 2

def check_learn_completion():
    """检测学习是否已完成（过渡页面）"""
    try:
        screenshot_path = os.path.join(SCREENSHOT_DIR, "learn_check.png")
        ImageGrab.grab().save(screenshot_path)
        
    except Exception as e:
        log.error(f"[检测异常] {e}")
    
    return False

def _parse_slash_progress(text):
    """从OCR文本中解析 '数字/数字' 格式，返回 (current, total) 或 (0, 0)"""
    m = re.search(r'(\d+)\s*/\s*(\d+)', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0

def _finish_learn_early(reason, done_flag_ref, thread_ref, t0_ref, shared_dict_ref, bank_dict_ref, bank_data_ref):
    """学习阶段提前结束的统一处理：设置完成标志、等待OCR线程、记录耗时、返回结果"""

    log.info(f"[学习] {reason}，提前结束本轮")
    done_flag_ref[0] = True
    thread_ref.join()
    elapsed = int(time.time() - t0_ref)
    log.info(f"[学习] 完成（提前结束），耗时 {format_td(elapsed)}")
    return shared_dict_ref, bank_dict_ref, bank_data_ref

def learn_30_words(first_round=False, start_local_idx=1, start_global_idx=1,
                   partial_dict=None, partial_bank=None,
                   dict_name=None, dict_bank_data=None, round_num=1):
    """
    学习30词 + 并行OCR
    参数:
        first_round: 是否首轮
        start_local_idx: 本组起始编号（1-30）
        start_global_idx: 词典起始编号
        partial_dict: 已有的部分词典（断点续传用）
        partial_bank: 已有的部分题库（断点续传用）
        dict_name: 词典名称
        dict_bank_data: 词典题库数据
    返回 (本轮词dict, 全局题库dict, 更新后的题库数据) 或 (None, None, None) 表示停止
    """
    log.info(f"[学习] 开始学习：本组第 {start_local_idx} 词，词典第 {start_global_idx} 词")
    # 登记本次运行覆盖的词典索引区间（供运行记录精确归档，用词典序号）
    try:
        run_record_note_range(start_global_idx, start_global_idx + max(0, GROUP_SIZE - start_local_idx))
    except Exception:
        pass
    global stop_flag

    shared_dict = partial_dict or {}
    bank_dict = partial_bank or {}
    queue = []
    done_flag = [False]
    lock = threading.Lock()
    same_word_count = 0
    last_word = ""
    
    # 词典题库
    current_dict_name = dict_name or "默认词汇表"
    current_dict_bank = dict_bank_data or {"dictionary_name": current_dict_name, "total_words": 0, "words": [], "confirmed": False, "expected_total": 2862}
    bank_word_count = len(current_dict_bank.get("words", []))
    # 逐词精简总闸：允许「库里已确定的词」直接取用（跳过截图+OCR）
    word_skip_ok = is_word_skip_enabled(current_dict_bank)
    # 词典库里已处于「已确定」状态的词数
    confirmed_word_count = count_confirmed_words(current_dict_bank)
    # 整本是否已确认
    bank_trusted = is_bank_trusted(current_dict_bank)
    # 等待精简：册内已有「已确定」的词就启用（跳过识别的词能省下更多时间）
    fast_waits_ok = bool(SMART_ENABLED and SMART_FAST_WAITS and confirmed_word_count > 0)
    bank_skip_count = [0]   # 本组从词典库直接取词的数量
    ocr_count = [0]         # 本组实际 OCR 识别的数量

    if word_skip_ok and confirmed_word_count > 0:
        log.info(f"[学习] 逐词精简已启用：'{current_dict_name}' 册内已确定的 {confirmed_word_count}/{bank_word_count} 词将跳过截图/OCR（其余词仍走OCR识别）")
        if fast_waits_ok:
            log.info(f"[学习] 等待精简已启用：跳过识别的词进度OCR每{SMART_PROGRESS_OCR_EVERY_N}词读一次，固定等待缩短")
    elif word_skip_ok:
        log.info(f"[学习] 逐词精简已开，但 '{current_dict_name}' 册内暂无「已确定」的词（共 {bank_word_count} 词）→ 本组全部走OCR，识别后入库存为未确定")
    else:
        log.info(f"[学习] 使用OCR模式: 无题库，将创建新题库")
    if bank_trusted:
        log.info(f"[学习] 整本词典已确认 → 同时启用等待精简（缩短固定等待、进度OCR降频）")

    def worker():
        processed = set()
        while not done_flag[0]:
            local_idx = global_idx = None
            with lock:
                if queue:
                    local_idx, global_idx = queue.pop(0)
            if local_idx is None or local_idx in processed:
                time.sleep(0.3)
                continue
            processed.add(local_idx)

            # 先查词典库：这个位置是否已经收录了词
            existing = get_word_from_bank(current_dict_bank, global_idx)
            already_logged = False

            # 逐词判定：该词已收录且「已确定」→ 直接从词典库取词，跳过截图/OCR
            recorded = get_recorded_word(current_dict_bank, global_idx, trusted=word_skip_ok)
            if recorded:
                with lock:
                    shared_dict[str(local_idx)] = recorded
                    bank_dict[str(global_idx)] = recorded
                    bank_skip_count[0] += 1
                log_word_already_recorded(global_idx, recorded['word'], recorded['meaning'],
                                          local_index=local_idx, source="直接从词典库取用")
                continue

            # 使用OCR（残缺题库也走OCR进行验证/补全/覆盖）
            wp = os.path.join(SAVE_DIR, f"word_{local_idx}.png")
            mp = os.path.join(SAVE_DIR, f"mean_{local_idx}.png")
            for _ in range(20):
                if os.path.exists(wp) and os.path.exists(mp):
                    break
                time.sleep(0.1)
            if not os.path.exists(wp) or not os.path.exists(mp):
                log.warning(f"  [worker] 截图文件不存在: word_{local_idx}.png，跳过")
                continue
            wt, _ = classify(ocr_file(wp))
            _, mt = classify(ocr_file(mp))
            if not wt and mt:
                wt, _ = classify(ocr_file(mp))
                _, mt = classify(ocr_file(wp))

            if not wt or not mt:
                log.warning(f"  [OCR失败] 本组第{local_idx}词，跳过该词")

            # 与题库对比：补全 / 覆盖 / 匹配 / 保留（existing 已在上面查过）
            if existing:
                old_word = existing.get("word", "")
                old_meaning = existing.get("meaning", "")
                if wt and wt != "[识别失败]":
                    if wt == old_word:
                        log_word_already_recorded(global_idx, wt, mt, local_index=local_idx,
                                                  source="OCR识别与库中记录一致")
                        already_logged = True
                    else:
                        log.info(f"  [覆盖 词典第{global_idx}词] '{old_word}' → '{wt}'")
                else:
                    # OCR失败，使用题库 fallback
                    wt = old_word
                    mt = old_meaning
                    log_word_already_recorded(global_idx, wt, mt, local_index=local_idx,
                                              source="OCR失败，改用词典库记录")
                    already_logged = True
            else:
                if wt and wt != "[识别失败]":
                    log.info(f"  [补全 词典第{global_idx}词] 新单词 '{wt}' 已添加到题库")
                else:
                    log.warning(f"  [失败 词典第{global_idx}词] OCR失败且题库无记录")

            entry = {"word": wt or "[识别失败]", "meaning": mt or "[识别失败]"}
            with lock:
                shared_dict[str(local_idx)] = entry
                bank_dict[str(global_idx)] = entry
                ocr_count[0] += 1
                # 记录到词典题库（覆盖或补全）
                if wt and mt and wt != "[识别失败]":
                    add_word_to_bank(current_dict_bank, global_idx, wt, mt)
            if not already_logged:
                log.info(f"  [OCR 本组第{local_idx}词 / 词典第{global_idx}词] {wt} | {mt}")

    t0 = time.time()

    for f in os.listdir(SAVE_DIR):
        if f.endswith('.png'):
            try:
                os.remove(os.path.join(SAVE_DIR, f))
            except:
                pass

    if first_round:
        _sleep(2)
    else:
        _sleep(20)
        page_status = ensure_page_loaded()
        if page_status == "testing":
            log.info("[学习] 当前已是测试页面，跳过学习阶段")
            return {}, {}, current_dict_bank
        elif page_status == "result":
            log.info("[学习] 当前是结果页面，本轮已完成，进入测试阶段")
            return {}, {}, current_dict_bank
        elif page_status == "task_list":
            log.info("[学习] 当前是任务列表页，重新检测页面状态")
            return {}, {}, current_dict_bank
        elif not page_status:
            log.error("[学习] 页面加载失败")
            return None, None, None
        if stop_flag:
            return None, None, None

    progress_text = ocr_region(REGION_WORD_INDEX)
    log.info(f"[总进度] OCR: '{progress_text}'")
    today_text = ocr_region(REGION_TODAY)
    log.info(f"[今日新词] OCR: '{today_text}'")
    
    global_done = 0
    global_done, _ = _parse_slash_progress(progress_text)
    if global_done > 0:
        log.info(f"[总进度] 已完成 {global_done} 词")
    
    today_current = 0
    today_total = 0
    today_current, today_total = _parse_slash_progress(today_text)
    if today_current > 0 and today_total > 0:
        log.info(f"[今日新词] 已完成 {today_current}/{today_total}")
    
    if start_global_idx == 1 and not first_round:
        if today_current > 0 and today_total > 0:
            # 用户公式: 组内偏移 = 30 - (today_total - today_current) + 1
            remaining_in_group = today_total - today_current
            offset_in_group = GROUP_SIZE - remaining_in_group + 1
            global_first = global_done + offset_in_group
            log.info(f"[总进度] 进度 {global_done} + 组内偏移 {offset_in_group} = 第 {global_first} 词")
        elif global_done > 0:
            global_first = global_done + 1
            log.info(f"[总进度] 进度 {global_done} + 1 = 第 {global_first} 词")
        else:
            global_first = start_global_idx
        
        start_local_idx = ((global_first - 1) % GROUP_SIZE) + 1
        start_global_idx = global_first
    elif not first_round and global_done > 0:
        # 非第一轮且有进度数据：用OCR校正传入的start_global_idx
        if today_current > 0 and today_total > 0:
            remaining_in_group = today_total - today_current
            offset_in_group = GROUP_SIZE - remaining_in_group + 1
            global_first = global_done + offset_in_group
            log.info(f"[总进度] OCR校正: 进度 {global_done} + 组内偏移 {offset_in_group} = 第 {global_first} 词 (原: {start_global_idx})")
            start_local_idx = ((global_first - 1) % GROUP_SIZE) + 1
            start_global_idx = global_first
    log.info(f"[学习] 起始：本组第 {start_local_idx} 词，词典第 {start_global_idx} 词")

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    i = start_local_idx
    global_i = start_global_idx
    first_word_text = None
    first_word_stuck = 0
    # 新一轮学习开始前，清掉上一轮可能残留的页面跳变标志
    _page_mismatch[0] = False

    # 重启后：如果上一个词正好是7的倍数（7/14/21/28），页面可能正停留在"继续背单词"界面
    if not first_round and i > 1 and (i - 1) % 7 == 0 and (i - 1) < GROUP_SIZE:
        log.info(f"[学习] 重启检测：上一个词是第{i-1}词(7的倍数)，可能需要点击'继续背单词'")
        _sleep(3)
        supervised_click(
            BTN_CONTINUE_LEARN[0], BTN_CONTINUE_LEARN[1],
            purpose="重启后点击'继续背单词'(上一个词是7的倍数)",
            detail=f"i={i}, 上一个词={i-1}, {i-1}%7=0"
        )
        _sleep(random.uniform(*LEARN_CLICK_RANGE))

    while i <= GROUP_SIZE:
        # 学习途中发现 App 已切到测试页（比如新词学完了），立即停止学习，
        # 保存进度，避免继续按学习页坐标乱点、丢词。
        if _page_mismatch[0]:
            _page_mismatch[0] = False
            log.warning(f"[学习] 检测到 App 已切到测试阶段，停止学习流程（已学到第 {i} 词）")
            done_flag[0] = True
            try:
                t.join(timeout=3)
            except Exception:
                pass
            save_progress(
                round_num=round_num,
                phase="learning",
                learn_local_index=i,
                learn_global_index=global_i,
                word_dict=shared_dict,
                bank_dict=bank_dict
            )
            return None, None, None

        if stop_flag:
            done_flag[0] = True
            t.join()
            save_progress(
                round_num=round_num,
                phase="learning",
                learn_local_index=i,
                learn_global_index=global_i,
                word_dict=shared_dict,
                bank_dict=bank_dict
            )
            return None, None, None

        save_progress(
            round_num=round_num,
            phase="learning",
            learn_local_index=i,
            learn_global_index=global_i,
            word_dict=shared_dict,
            bank_dict=bank_dict,
            dict_name=current_dict_name
        )

        # 逐词判定：这个词是否已收录且已确定（已确定才跳过识别）
        recorded_now = get_recorded_word(current_dict_bank, global_i, trusted=word_skip_ok)
        skip_ocr = recorded_now is not None

        if skip_ocr:
            log.info(f"  [本组第{i}/30词，词典第{global_i}词] 已收录 → 跳过截图/OCR")
        else:
            log.info(f"  [本组第{i}/30词，词典第{global_i}词] 截图...")


        read_time = random.uniform(*LEARN_READ_RANGE)
        log.debug(f"[学习阅读] 看单词 {read_time:.1f} 秒")

        supervised_click(BTN_VIEW[0], BTN_VIEW[1], purpose="点击查看释义")
        if skip_ocr:
            # 已收录：不截图、不OCR，但需等待页面加载完成
            wait_page_loaded(timeout=3)
            # 每7个词做OCR校验，确保脚本运行与实际情况一致
            if i % 7 == 0:
                log.info(f"  [校验] 第{i}词(7的倍数)，进行OCR校验...")
                _sleep(0.5)
                ImageGrab.grab(bbox=REGION_WORD).save(os.path.join(SAVE_DIR, f"verify_word_{i}.png"))
                _move_away()
                ImageGrab.grab(bbox=REGION_MEAN).save(os.path.join(SAVE_DIR, f"verify_mean_{i}.png"))
                actual_word_raw = ocr_region(REGION_WORD)
                actual_meaning_raw = ocr_region(REGION_MEAN)
                actual_w, _ = classify(actual_word_raw)
                _, actual_m = classify(actual_meaning_raw)
                expected_w = recorded_now.get('word', '')
                expected_m = recorded_now.get('meaning', '')
                if actual_w and actual_w != expected_w:
                    log.warning(f"  [校验⚠️] 单词不符！词典:{expected_w} → 实际:{actual_w}")
                    with lock:
                        add_word_to_bank(current_dict_bank, global_i, actual_w, actual_m or expected_m)
                elif actual_m and actual_m != expected_m:
                    log.warning(f"  [校验⚠️] 释义不符！词典:{expected_m} → 实际:{actual_m}")
                    with lock:
                        add_word_to_bank(current_dict_bank, global_i, actual_w or expected_w, actual_m)
                else:
                    log.info(f"  [校验✓] 单词+释义匹配：{actual_w or expected_w} | {actual_m or expected_m}")
            else:
                log.info(f"  [精简] 词典第{global_i}词 '{recorded_now['word']}' 已在词典库，跳过识别（省 2 张截图 + OCR）")
        else:
            _sleep(random.uniform(0.8, 1.5))
            ImageGrab.grab(bbox=REGION_WORD).save(os.path.join(SAVE_DIR, f"word_{i}.png"))
            _move_away()
            ImageGrab.grab(bbox=REGION_MEAN).save(os.path.join(SAVE_DIR, f"mean_{i}.png"))

        # 进度 OCR 降频：跳过识别的词每 N 词读一次（仍需识别的词照旧每词读）
        do_progress_ocr = True
        if SMART_ENABLED and SMART_PROGRESS_OCR_EVERY_N > 0 and word_skip_ok:
            if skip_ocr and ((i - start_local_idx + 1) % SMART_PROGRESS_OCR_EVERY_N != 0):
                do_progress_ocr = False
        if do_progress_ocr:
            progress = ocr_word_index()
            if progress:
                log.info(f"  [总进度] {progress}")

        with lock:
            queue.append((i, global_i))

        supervised_click(BTN_EASY[0], BTN_EASY[1], purpose="点击'太简单'按钮标记单词")
        # 精简模式等待下一个单词页面加载
        if skip_ocr:
            wait_page_loaded(timeout=3)
        else:
            _sleep(random.uniform(0.2, 0.5))

        # 每7个单词后需要点击"继续背单词"按钮
        if i % 7 == 0 and i < GROUP_SIZE:
            log.info(f"  [学习] 已学完 {i} 个单词，点击'继续背单词'按钮...")
            _sleep(SMART_CONTINUE_WAIT if fast_waits_ok else 3)
            supervised_click(
                BTN_CONTINUE_LEARN[0], BTN_CONTINUE_LEARN[1],
                purpose="点击'继续背单词'按钮",
                detail=f"已学完第{i}个单词，点击继续背单词进入下一批"
            )
        elif i < GROUP_SIZE:
            view_x = BTN_VIEW[0] + random.randint(-10, 10)
            view_y = BTN_VIEW[1] + random.randint(-10, 10)
            supervised_click(view_x, view_y, purpose="点击查看释义（下一个单词）")
        else:
            # 最后一个词（i == GROUP_SIZE）：不点击"下一个单词"，直接退出循环
            # 由后续代码点击"继续背单词"进入测试阶段
            log.info(f"  [学习] 已学完最后 1 个单词（第{i}词），准备进入测试阶段...")

        # 等 worker 回填本词：已收录的词是秒回填，等待可以更短
        if skip_ocr:
            wait_rounds, wait_gap = 8, (0.1, 0.2)
        else:
            wait_rounds, wait_gap = 30, (0.2, 0.5)
        for _ in range(wait_rounds):
            with lock:
                w = shared_dict.get(str(i), {}).get("word", "")
                m = shared_dict.get(str(i), {}).get("meaning", "")
            if w and w != "[识别失败]":
                break
            time.sleep(random.uniform(*wait_gap))

        # 检测学习完成过渡页面
        if w and ("学习完成" in w or "跳转" in w or "秒后" in w):
            log.warning(f"  [检测] 识别到过渡页面内容: '{w}'")
            log.info("[学习] 可能已完成本轮学习，等待页面跳转...")
            _sleep(8)
            
            if check_learn_completion():
                return _finish_learn_early("确认学习完成", done_flag, t, t0, shared_dict, bank_dict, current_dict_bank)
            else:
                log.warning("[学习] 未确认完成，继续学习...")

        if i == start_local_idx and w and w != "[识别失败]":

            if first_word_text is None:
                first_word_text = w
            elif w.strip() == first_word_text.strip():
                first_word_stuck += 1
                log.warning(f"  [卡住] 第一个词 '{w}' 重复 {first_word_stuck} 次")
                if first_word_stuck >= 2:
                    log.warning("[学习] 第一个词连续卡住，尝试重启...")
                    restart_result = _restart_learn_flow()
                    if restart_result is False:
                        log.error("[学习] 重启失败，本轮学习结束")
                        done_flag[0] = True
                        t.join()
                        return None, None, None
                    if restart_result in ("testing", "result"):
                        log.info(f"[学习] 重启后检测到{restart_result}页面，提前结束学习")
                        return _finish_learn_early(f"检测到{restart_result}页面", done_flag, t, t0, shared_dict, bank_dict, current_dict_bank)
                    first_word_text = None
                    first_word_stuck = 0
                    i = start_local_idx
                    global_i = start_global_idx
                    continue
            else:
                first_word_text = w
                first_word_stuck = 0

        if i > start_local_idx:
            with lock:
                prev_w = shared_dict.get(str(i-1), {}).get("word", "")
                curr_w = shared_dict.get(str(i), {}).get("word", "")
                curr_m = shared_dict.get(str(i), {}).get("meaning", "")
            
            # 检测学习完成过渡页面（通过meaning字段）
            if curr_m and is_learning_complete(curr_m):
                log.warning(f"  [检测] meaning中识别到学习完成内容: '{curr_m[:30]}...'")
                log.info("[学习] 检测到学习完成过渡页面，等待跳转...")
                _sleep(8)
                
                if check_learn_completion():
                    log.info("[学习] 确认学习完成，提前结束本轮")
                    done_flag[0] = True
                    t.join()
                    elapsed = int(time.time() - t0)
                    log.info(f"[学习] 完成（提前结束），耗时 {format_td(elapsed)}")
                    return shared_dict, bank_dict, current_dict_bank

            prev_is_empty = not prev_w or prev_w.strip() == "" or "[识别失败]" in prev_w
            curr_is_empty = not curr_w or curr_w.strip() == "" or "[识别失败]" in curr_w
            
            # 连续3次相同单词，可能是卡住了或过渡页面
            if w and w == last_word:
                same_word_count += 1
                log.warning(f"  [连续重复] 单词 '{w}' 已连续出现 {same_word_count} 次")
                if same_word_count >= 3:
                    log.warning("[学习] 连续3次相同单词，检测页面状态...")
                    if check_learn_completion():
                        return _finish_learn_early("检测到学习完成", done_flag, t, t0, shared_dict, bank_dict, current_dict_bank)
                    else:
                        log.warning("[学习] 未检测到完成页面，尝试重启...")
                        restart_result = _restart_learn_flow()
                        if restart_result is False:
                            log.error("[学习] 重启失败，本轮学习结束")
                            done_flag[0] = True
                            t.join()
                            return None, None, None
                        if restart_result in ("testing", "result"):
                            log.info(f"[学习] 重启后检测到{restart_result}页面，提前结束学习")
                            return _finish_learn_early(f"检测到{restart_result}页面", done_flag, t, t0, shared_dict, bank_dict, current_dict_bank)
                        same_word_count = 0
                        i = start_local_idx
                        global_i = start_global_idx
                        first_word_text = None
                        first_word_stuck = 0

                        # 重启成功后，检测页面实际显示的是第几个词
                        progress_text = ocr_word_index()
                        if progress_text:
                            current_pos, total = _parse_slash_progress(progress_text)
                            if current_pos > 0 and current_pos != i:
                                log.info(f"[重启] 页面实际进度为第{current_pos}/{total}词，修正索引")
                                i = current_pos
                                global_i = start_global_idx + (current_pos - start_local_idx)

                        continue
            else:
                same_word_count = 0
                last_word = w
            
            if prev_is_empty and curr_is_empty:
                log.warning(f"  [跳过] 连续两个词识别失败，跳过当前词")
            elif not prev_is_empty and not curr_is_empty and curr_w.strip() == prev_w.strip():
                log.warning(f"  [重复] 回退重试")
                i -= 1
                global_i -= 1
                continue

        stats["total_words_learned"] += 1
        
        # 每学完一个就保存词典文件，确保断点续传后测试阶段能读到
        try:
            with open(WORD_DICT, 'w', encoding='utf-8') as f:
                json.dump(shared_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"  [保存] 词典文件写入失败: {e}")
        
        i += 1
        global_i += 1

    done_flag[0] = True
    while True:
        with lock:
            if not queue:
                break
        time.sleep(0.5)
    t.join()

    elapsed = int(time.time() - t0)
    log.info(f"[学习] 完成，耗时 {format_td(elapsed)}")
    if bank_skip_count[0] or ocr_count[0]:
        log.info(f"[精简统计] 本组 {bank_skip_count[0]} 词直接从词典库取用（省 {bank_skip_count[0]*2} 张截图 + {bank_skip_count[0]*2} 次OCR），{ocr_count[0]} 词实际走了OCR识别")

    # 学习完成后点击"继续背单词"进入下一阶段
    log.info("[学习] 点击'继续背单词'进入测试阶段...")
    _sleep(SMART_FINISH_WAIT if fast_waits_ok else 3)
    supervised_click(
        BTN_CONTINUE_LEARN[0], BTN_CONTINUE_LEARN[1],
        purpose="点击'继续背单词'进入测试",
        detail="30个单词学习完成，点击继续背单词进入测试阶段"
    )
    _sleep(random.uniform(2, 4))
    
    # 保存词典题库
    if current_dict_bank and current_dict_name:
        save_dictionary_bank(current_dict_name, current_dict_bank)
    
    return shared_dict, bank_dict, current_dict_bank


# ================= 模糊匹配 =================
def _clean_en_token(text):
    """从 OCR 文本里挑出像英文单词的部分"""
    t = text.strip().strip('.,;:!?"“”‘’()（）[]【】')
    t = t.replace(' ', '')
    return re.sub(r"[^A-Za-z\-']", '', t)

# 释义里常见的词性缩写；OCR 会把 adj. 认成 adi，必须过滤掉
_POS_ABBRS = {"n", "v", "vt", "vi", "adj", "adv", "prep", "conj",
              "pron", "num", "art", "int", "interj", "pl", "abbr", "aux",
              "adi", "adl", "ad"}

def _contains_cjk(text):
    """判断一段文字里有没有中文（有中文基本就是释义行，不是单词行）"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in str(text))

def ocr_screen_word(word_dict=None):
    """
    认出测试页当前显示的目标单词（英文），用于取代「按题号猜词表」
    ① 校准过单词区域就直接认该区域；② 否则全屏 OCR，并优先选择词表/总题库里真实存在的词
    """
    def pick(text):
        c = _clean_en_token(text)
        raw = text.strip()
        if 2 <= len(c) <= 24 and raw and len(c) >= len(raw) * 0.6:
            return c.lower()
        return None

    if TEST_WORD_REGION:
        w = pick(ocr_region(TEST_WORD_REGION))
        if w:
            log.info(f"[单词识别] 区域识别: '{w}'")
            return w
        log.warning("[单词识别] 已配置单词区域但没认出英文，改用全屏定位")

    try:
        blocks = ocr_full_screen()
    except Exception as e:
        log.warning(f"[单词识别] 全屏OCR失败: {e}")
        return None

    y_top = REGION_QUESTION_TYPE[3] if REGION_QUESTION_TYPE else 200
    y_bottom = REGION_OPTION[0][1] if REGION_OPTION else 388
    x_left = (min(r[0] for r in REGION_OPTION) if REGION_OPTION else 1400) - 100

    cands = []
    for b in blocks:
        w = pick(b.get("text", ""))
        if not w:
            continue
        y = b.get("y", 0)
        if b.get("x", 0) < x_left:
            continue
        if y_top - 20 <= y <= y_bottom:
            cands.append((y, w))
    if not cands:
        for b in blocks:
            # 兜底也不能把助手窗口的文字当成题目内容（"内置 Rapid" 就是这么被认错的）
            if b.get("x", 0) < ONECLASS_X_MIN:
                continue
            w = pick(b.get("text", ""))
            if w:
                cands.append((b.get("y", 0), w))
    if not cands:
        log.warning("[单词识别] 全屏OCR没找到英文单词")
        return None

    # 候选里可能混着界面上的英文标签（例如 Rapid/OneClass）。
    # 优先选「本组词表 / 总题库里真实存在」的词，而不是只按屏幕位置取最上面那个。
    group_words = set()
    if isinstance(word_dict, dict):
        for item in word_dict.values():
            if isinstance(item, dict):
                w = str(item.get("word", "")).strip().lower()
                if w:
                    group_words.add(w)

    scored = []
    for y, w in cands:
        score = 0
        if w in group_words:
            score += 10
        try:
            m, _src = lookup_word_meaning(w, word_dict)
            if m:
                score += 4
        except Exception:
            pass
        scored.append((score, -y, w, y))

    scored.sort(reverse=True)
    log.info(
        "[单词识别] 候选评分: "
        + ", ".join(f"{w}({score})" for score, _ny, w, _y in scored[:5])
    )
    return scored[0][2]

_BANK_WORDS_CACHE = {}

def lookup_word_meaning(word, word_dict=None):
    """用单词查释义：①本组词表 ②总题库。返回 (释义, 来源)，查不到返回 (None, None)"""
    if not word:
        return None, None
    w = str(word).strip().lower()

    if isinstance(word_dict, dict):
        for item in word_dict.values():
            if isinstance(item, dict) and str(item.get('word', '')).strip().lower() == w:
                m = item.get('meaning', '')
                if m and m != '[缺失]':
                    return m, '本组词表'

    try:
        if 'bank' not in _BANK_WORDS_CACHE:
            words = []
            for f in sorted(BANK_DIR.glob('题库_*.json')):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    words.extend(data.get('words', []) or [])
                except Exception:
                    continue
            bank = {}
            for x in words:
                _w = str(x.get('word', '')).strip().lower()
                _m = x.get('meaning', '') or ''
                if not _w or not _m:
                    continue
                if not re.search(r'[\u4e00-\u9fff]', _m):
                    continue          # 跳过纯英文/乱码的脏释义
                if _w not in bank:
                    bank[_w] = _m    # 重复单词保留第一条
            _BANK_WORDS_CACHE['bank'] = bank
            log.info(f"[查词] 已加载总题库 {len(_BANK_WORDS_CACHE['bank'])} 词")
        m = _BANK_WORDS_CACHE['bank'].get(w)
        if m:
            return m, '总题库'
    except Exception as e:
        log.warning(f"[查词] 读取总题库失败: {e}")
    return None, None

def fuzzy_contains(text, keyword, threshold=FUZZY_TYPE_THRESHOLD):
    if keyword in text:
        return True, 1.0
    kw_len = len(keyword)
    text_len = len(text)
    if kw_len == 0 or text_len == 0:
        return False, 0.0
    max_ratio = 0.0
    for i in range(max(0, text_len - kw_len * 2) + 1):
        for ws in range(max(1, kw_len - 2), min(text_len - i + 1, kw_len + 3)):
            ratio = SequenceMatcher(None, text[i:i+ws], keyword).ratio()
            if ratio > max_ratio:
                max_ratio = ratio
    return max_ratio >= threshold, max_ratio

def fuzzy_match_best(text, keywords, threshold=FUZZY_TYPE_THRESHOLD):
    best_kw, best_score = None, 0.0
    for kw in keywords:
        matched, score = fuzzy_contains(text, kw, threshold)
        if matched and score > best_score:
            best_kw, best_score = kw, score
    return best_kw, best_score

# 词性标记：n. / v. / adj. / adv. 等
_POS_RE = re.compile(r'\b(n|v|vt|vi|adj|a|adv|prep|conj|pron|num|art|int|aux)\.?(?=\s|$|[^A-Za-z])', re.IGNORECASE)


def _split_pos_and_cn(text):
    """把 'v.诅咒；adj.该死的' 拆成 (词性集合, 中文片段列表)"""
    t = str(text or '').lower()
    pos = set()
    for m in _POS_RE.finditer(t):
        p = m.group(1).lower()
        if p in ('vt', 'vi'):
            p = 'v'
        elif p == 'a':
            p = 'adj'
        pos.add(p)
    cn = _POS_RE.sub(' ', t)
    cn = re.sub(r'[^\u4e00-\u9fff]+', ' ', cn)
    parts = [x for x in cn.split() if x]
    return pos, parts


def _cn_overlap(parts_a, parts_b):
    """A 的每个中文片段是否能在 B 里找到（包含关系）；返回命中比例"""
    if not parts_a or not parts_b:
        return 0.0
    hit = 0
    for a in parts_a:
        for b in parts_b:
            if a in b or b in a:
                hit += 1
                break
    return hit / len(parts_a)


def fuzzy_option_match(meaning, options, threshold=FUZZY_OPTION_THRESHOLD):
    """改进版：词性 + 中文关键词分段匹配。

    为什么改：旧版用整句相似度，题库释义和屏幕选项措辞稍有不同就会被判为
    「没匹配上」。现在拆成三部分打分：
      · 词性是否一致（权重 0.25）
      · 中文关键词是否重叠（权重 0.55）
      · 整句相似度（权重 0.20，辅助）
    """
    if not meaning:
        return None, 0.0

    m_pos, m_parts = _split_pos_and_cn(meaning)
    mc = ''.join(m_parts)

    best_idx, best_score = None, 0.0
    pos_hits = []
    for i, opt in enumerate(options):
        if not opt:
            continue
        o_pos, o_parts = _split_pos_and_cn(opt)
        oc = ''.join(o_parts)

        # 完全包含：直接满分
        if mc and oc and (mc in oc or oc in mc):
            return i, 1.0

        # 1) 词性匹配
        pos_score = 1.0 if (m_pos and o_pos and (m_pos & o_pos)) else 0.0

        # 2) 中文关键词重叠
        cn_score = _cn_overlap(m_parts, o_parts)

        # 3) 整句相似度（辅助）
        sim = SequenceMatcher(None, oc, mc).ratio() if (mc and oc) else 0.0

        if pos_score > 0:
            pos_hits.append(i)
        score = 0.25 * pos_score + 0.55 * cn_score + 0.20 * sim
        log.debug(
            f"[匹配] 选项{chr(65+i)}: 词性={pos_score:.2f} 关键词={cn_score:.2f} "
            f"整句={sim:.2f} 综合={score:.2f} | '{opt[:30]}'"
        )
        if score > best_score:
            best_score = score
            best_idx = i

    # 兜底：如果只有一个选项的词性和题目释义对得上，就认为是它。
    # 例：题目释义含 a.(形容词)，四个选项里只有 D 是 adj.
    if best_idx is not None and len(pos_hits) == 1 and pos_hits[0] == best_idx:
        log.info(f"[匹配] 只有选项{chr(65+best_idx)}的词性与题目一致，按它来")
        return best_idx, max(best_score, 0.40)

    if best_score >= threshold:
        return best_idx, best_score
    return None, best_score

def detect_type_by_image():
    if not IMAGE_DETECT_ENABLED:
        return None
    try:
        variances = []
        for region in REGION_OPTION:
            gray = ImageGrab.grab(bbox=region).convert('L')
            px = list(gray.getdata())
            avg = sum(px) / len(px)
            variances.append(sum((p - avg)**2 for p in px) / len(px))
        high = sum(1 for v in variances if v > 2000)
        if high >= 3:
            return '选择题'
        if high <= 1:
            return '拼写题'
        return None
    except Exception as e:
        log.debug(f"[图像检测] 失败: {e}")
        return None


# ================= 截图管理 =================
screenshot_count = 0

def save_screenshot(region, qn, qtype):
    global screenshot_count
    img = ImageGrab.grab(bbox=region)
    ts = datetime.now().strftime('%H%M%S')
    tmap = {'拼写': 'spelling', 'spelling': 'spelling',
            '选择': 'choice', 'choice': 'choice', '题号': 'number'}
    te = tmap.get(qtype.replace('选项', ''), qtype or 'unknown')
    fp = SCREENSHOT_DIR / f"{qn:02d}_{te}_{ts}.png"
    img.save(fp)
    screenshot_count += 1
    log.debug(f"[截图] 保存: {fp.name}")

def cleanup_screenshots():
    for f in SCREENSHOT_DIR.glob("*.png"):
        try:
            f.unlink()
        except:
            pass


# ================= 阶段2：测试 =================
def get_question_number():
    time.sleep(0.5)
    text = ocr_region(REGION_NUMBER)
    log.debug(f"[题号OCR] 区域 {REGION_NUMBER}: '{text}'")
    
    for pat in [r'(\d+)\s*/\s*(\d+)', r'(\d+)\s*[^\d]+\s*(\d+)']:
        m = re.search(pat, text)
        if m:
            n = int(m.group(1)) + 1
            save_screenshot(REGION_NUMBER, n, "题号")
            return n
    
    if not text.strip():
        text = ocr_region((REGION_NUMBER[0], REGION_NUMBER[1]-20, REGION_NUMBER[2], REGION_NUMBER[3]))
        for pat in [r'(\d+)\s*/\s*(\d+)', r'(\d+)\s*[^\d]+\s*(\d+)']:
            m = re.search(pat, text)
            if m:
                n = int(m.group(1)) + 1
                return n
    
    
    return None

def determine_question_type(question_num):
    img_type = detect_type_by_image()
    time.sleep(0.2)
    type_text = ocr_region(REGION_QUESTION_TYPE)
    log.debug(f"[题型识别] OCR文本: '{type_text}'，图像检测: {img_type}")

    spelling_kw, spelling_score = fuzzy_match_best(type_text,
        ['请填写你听到的单词', '听到的单词', '请拼写', '听力', '拼写', '填写'])
    choice_kw, choice_score = fuzzy_match_best(type_text,
        ['请选择正确的释义', '选择正确的', '选择正确', '正确的释义', '释义', '选择题'])

    qt = None
    diff = abs(choice_score - spelling_score)
    if diff > 0.3 and choice_score > 0.7:
        qt = '选择题'
    elif diff > 0.3 and spelling_score > 0.7:
        qt = '拼写题'

    if qt is None and img_type:
        if img_type == '拼写题' and spelling_score > 0.4:
            qt = '拼写题'
        elif img_type == '选择题' and choice_score > 0.4:
            qt = '选择题'

    if qt is None:
        if spelling_score >= choice_score and spelling_score >= FUZZY_TYPE_THRESHOLD:
            qt = '拼写题'
        elif choice_score >= FUZZY_TYPE_THRESHOLD:
            qt = '选择题'
        elif spelling_score >= 0.3:
            qt = '拼写题'
        elif choice_score >= 0.3:
            qt = '选择题'
    if qt is None:
        qt = '选择题'

    save_screenshot(REGION_QUESTION_TYPE, question_num, qt)
    log.info(f"[题型] 判定为 {qt} (拼写分:{spelling_score:.2f}, 选择分:{choice_score:.2f})")
    return qt

def _fb_save_record(rec):
    """把一次反馈记录追加到 logs/拼写反馈记录.jsonl，方便事后分析"""
    try:
        with open(FB_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log.debug(f"[反馈] 记录写入失败: {e}")


def _repair_word_dict(qn, correct_word):
    """答错后把屏幕给的正确单词写回词表文件，以后同一题号不再答错"""
    try:
        fp = Path(WORD_DICT)
        d = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        old = ""
        item = d.get(str(qn))
        if isinstance(item, dict):
            old = item.get("word", "")
            item["word"] = correct_word
        else:
            d[str(qn)] = {"word": correct_word, "meaning": ""}
        fp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"[词表修正] 第{qn}题 '{old}' -> '{correct_word}'（已写回词表）")
    except Exception as e:
        log.debug(f"[词表修正] 失败: {e}")


# ================= 听音识别：录音 → 转文字 → 对词表 =================
_ASR_MODEL_CACHE = {"name": None, "model": None}


def asr_status_text():
    """给界面用的一句话：听音功能现在能不能用"""
    if _ASR_AVAILABLE:
        return f"可用（模型 {ASR_MODEL}）"
    miss = []
    if not _SOUNDCARD_AVAILABLE:
        miss.append("soundcard")
    if not _FASTER_WHISPER_AVAILABLE:
        miss.append("faster-whisper")
    return "不可用，缺: " + "、".join(miss)


def get_whisper_model():
    """第一次用到时才加载语音识别模型（要下载，慢，所以放后台）"""
    if not _FASTER_WHISPER_AVAILABLE:
        return None
    if _ASR_MODEL_CACHE["model"] is not None and _ASR_MODEL_CACHE["name"] == ASR_MODEL:
        return _ASR_MODEL_CACHE["model"]
    try:
        log.info(f"[ASR] 正在加载语音识别模型 {ASR_MODEL}（第一次要下载，请稍等）...")
        m = _WhisperModel(ASR_MODEL, device="cpu", compute_type="int8")
        _ASR_MODEL_CACHE["name"] = ASR_MODEL
        _ASR_MODEL_CACHE["model"] = m
        log.info("[ASR] 模型加载完成")
        return m
    except Exception as e:
        log.warning(f"[ASR] 模型加载失败: {e}")
        return None


def list_loopback_mics():
    """列出电脑上能用的录音设备；带 isloopback 的才能录到「电脑内部播放的声音」"""
    if not _SOUNDCARD_AVAILABLE:
        return []
    try:
        out = []
        for i, m in enumerate(sc.all_microphones(include_loopback=True)):
            out.append({"index": i, "id": getattr(m, "id", ""),
                        "name": str(m.name), "loopback": bool(getattr(m, "isloopback", False))})
        return out
    except Exception as e:
        log.debug(f"[ASR] 列举录音设备失败: {e}")
        return []


def _pick_loopback_device(device_name=None):
    """挑一个录音设备：优先用你指定的，其次挑能录系统声音的（回环）"""
    if not _SOUNDCARD_AVAILABLE:
        return None
    try:
        mics = sc.all_microphones(include_loopback=True)
    except Exception as e:
        log.warning(f"[ASR] 无法列举录音设备: {e}")
        return None
    if not mics:
        return None
    if device_name:
        for m in mics:
            if str(m.name) == str(device_name) or getattr(m, "id", "") == str(device_name):
                return m
    for m in mics:
        if getattr(m, "isloopback", False):
            return m
    return mics[0]


def record_system_audio(seconds=None, device_name=None):
    """
    录一段「电脑内部播放的声音」（就是 App 读单词的声音，不是你说话的声音）。
    返回 (音频数据, 采样率)；失败返回 (None, 0)。
    """
    sec = ASR_RECORD_SEC if seconds is None else float(seconds)
    dev = _pick_loopback_device(device_name)
    if dev is None:
        log.warning("[ASR] 找不到能录音的设备")
        return None, 0
    try:
        import numpy as np
        sr = int(getattr(dev, "samplerate", 48000) or 48000)
        sr = max(8000, min(sr, 96000))
        with dev.recorder(samplerate=sr, channels=1) as rec:
            data = rec.record(numframes=int(sec * sr))
        a = np.asarray(data, dtype=np.float32)
        if a.ndim > 1:
            a = a.mean(axis=1)
        a = a.astype(np.float32)
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        log.info(f"[ASR] 录了 {sec:.1f} 秒 | 设备='{dev.name}' | 最大音量={peak:.4f}")
        if peak < 1e-4:
            log.warning("[ASR] 录到的几乎是静音，请检查音量，或在界面上换个录音设备")
        return a, sr
    except Exception as e:
        log.warning(f"[ASR] 录音失败: {e}")
        return None, 0


def _resample(audio, orig_sr, target_sr=16000):
    """把录音的采样率统一成 16000（语音识别模型只认这个）"""
    try:
        import numpy as np
    except Exception:
        return audio
    if audio is None or orig_sr <= 0 or orig_sr == target_sr or audio.size < 2:
        return audio
    n = int(round(audio.shape[0] * target_sr / float(orig_sr)))
    if n <= 1:
        return audio
    x_old = np.linspace(0.0, 1.0, num=audio.shape[0], endpoint=False, dtype=np.float32)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False, dtype=np.float32)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def asr_transcribe(audio, sample_rate):
    """把一段录音转成英文文字"""
    if audio is None or audio.size == 0:
        return ""
    model = get_whisper_model()
    if model is None:
        return ""
    try:
        a16 = _resample(audio, sample_rate, 16000)
        # vad_filter 必须开：实测过，录到静音时不开它，Whisper 会自己瞎编
        # （静音 3 秒能编出 "You" / 一长串 "no no no"），编出来的词万一碰巧
        # 在本组词表里，拼写题就白白答错了。开了之后静音会老老实实返回空。
        segments, _info = model.transcribe(
            a16, language="en", beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        return " ".join(str(getattr(s, "text", "") or "").strip()
                        for s in segments).strip()
    except Exception as e:
        log.warning(f"[ASR] 识别失败: {e}")
        return ""


def asr_listen(seconds=None, device_name=None):
    """录一段系统声音并转成文字（界面「试录识别」和拼写题都走这里）"""
    _wait_if_paused()
    if stop_flag:
        return ""
    audio, sr = record_system_audio(seconds, device_name)
    if audio is None:
        return ""
    return asr_transcribe(audio, sr)


def asr_pick_word(text, group_words):
    """
    从听出来的话里挑出「本组词表里真的有」的那个词。
    先精确比对，比对不上再做模糊比对（容错 Whisper 听错一两个字母）。
    """
    if not text or not group_words:
        return None
    toks = [t.lower() for t in
            (_clean_en_token(x) for x in re.findall(r"[A-Za-z][A-Za-z'\-]*", text))]
    toks = [t for t in toks if len(t) >= 2]
    if not toks:
        return None
    gset = {}
    for w in group_words:
        w = str(w).strip()
        if w:
            gset[w.lower()] = w
    for t in toks:
        if t in gset:
            return gset[t]
    try:
        import difflib as _dl
        for t in toks:
            close = _dl.get_close_matches(t, list(gset.keys()), n=1, cutoff=ASR_MATCH_CUTOFF)
            if close:
                log.info(f"[ASR] 听到的 '{t}' 不在词表，最接近的是 '{close[0]}'，按它来")
                return gset[close[0]]
    except Exception:
        pass
    return None


def try_asr_for_spelling(qn, group_words):
    """
    拼写题专用：听一遍 App 的发音，认出这一题到底考哪个词。

    流程：
      1. 录一段系统内部声音 → 语音识别成文字
      2. 认出的词在本组词表里 → 直接用它（最准）
      3. 不在词表 → 点一下喇叭图标重播，再录再听一次
      4. 两次都对不上 → 返回 None，主流程退回「按词表顺序填」

    返回 (word, source)；source 只是用来打日志：asr = 第一次就听准 / asr_replay = 重播后听准
    """
    if not _ASR_AVAILABLE or not group_words:
        return None

    t1 = asr_listen()
    if t1:
        log.info(f"[ASR] 第{qn}题 第一次听到: '{t1}'")
        w = asr_pick_word(t1, group_words)
        if w:
            return w, "asr"
    else:
        log.warning(f"[ASR] 第{qn}题 第一次没听到声音")

    if not ASR_REPLAY_ON_FAIL:
        return None
    if not BTN_SPEAKER_REPLAY:
        log.warning("[ASR] 想重播，但没配喇叭图标坐标（config.json 里 regions.test.btn_speaker_replay）")
        return None

    log.info(f"[ASR] 第{qn}题 没对上词表，点喇叭重播再听一次...")
    try:
        click(BTN_SPEAKER_REPLAY, 0.4, purpose="重播单词读音（喇叭）")
    except Exception as e:
        log.warning(f"[ASR] 点喇叭失败: {e}")
        return None

    t2 = asr_listen()
    if not t2:
        log.warning(f"[ASR] 第{qn}题 重播后还是没听到声音")
        return None
    log.info(f"[ASR] 第{qn}题 第二次听到: '{t2}'")
    w2 = asr_pick_word(t2, group_words)
    if w2:
        return w2, "asr_replay"
    log.warning(f"[ASR] 第{qn}题 两次都对不上词表（'{t1}' / '{t2}'）")
    return None


def read_answer_feedback(question_num, typed_word):
    """
    拼写题答完点确认后，读「正确答案反馈区」。

    真机验证（2026-10-19）：OneClass 答错后会在固定位置显示
      正确单词（y约560）+ 中文释义（y约621）；答对时这块区域没有英文单词。
    所以判断方法很简单：反馈区出现「不是自己刚打进去的」英文单词 = 答错，它就是正确答案。

    返回 (status, correct_word, raw_text)
      status       : 'right' 答对 / 'wrong' 答错 / 'unknown' 没看出来
      correct_word : 答错时屏幕给出的正确拼写（读不到就是 None）
    """
    if not FB_ENABLED:
        return "unknown", None, ""
    try:
        time.sleep(FB_WAIT)
        if FB_SAVE_SHOT:
            try:
                ImageGrab.grab().save(
                    FB_SHOT_DIR / f"{question_num:02d}_{datetime.now().strftime('%H%M%S')}.png")
            except Exception as e:
                log.debug(f"[反馈] 截图失败: {e}")
        if FB_REGION:
            blocks = ocr_full_screen(FB_REGION)
        else:
            # 没配区域就全屏，但必须过滤掉助手窗口（x < ONECLASS_X_MIN）
            blocks = [b for b in ocr_full_screen()
                      if b.get("x", 0) >= ONECLASS_X_MIN]
    except Exception as e:
        log.warning(f"[反馈] OCR失败: {e}")
        return "unknown", None, ""

    raw = " | ".join(str(b.get("text", "")).strip() for b in blocks
                     if str(b.get("text", "")).strip())
    log.info(f"[反馈探测] 第{question_num}题 反馈区文字: {raw[:300]}")

    typed = _clean_en_token(typed_word or "").lower()

    # 核心判断：只从“单词行”里取词。
    # 带中文的是释义行，里面的 adj./adv. 被 OCR 认成 adi 时不能当答案。
    correct_word = None
    for b in sorted(blocks, key=lambda z: z.get("y", 0)):
        block_text = str(b.get("text", "")).strip()
        if _contains_cjk(block_text):
            continue
        w = _clean_en_token(block_text)
        if (3 <= len(w) <= 24 and w.lower()
                and w.lower() not in _POS_ABBRS and w.lower() != typed):
            correct_word = w.lower()
            break

    # 关键词只是辅助，且只在反馈区内找，不会被助手窗口的"非故意答错率"误伤
    low = raw.lower()
    wrong_hit = next((k for k in FB_WRONG_KW if str(k).lower() in low), None)
    right_hit = next((k for k in FB_RIGHT_KW if str(k).lower() in low), None)

    if correct_word or wrong_hit:
        status = "wrong"
    elif right_hit:
        status = "right"
    else:
        status = "unknown"

    if correct_word:
        log.warning(f"[反馈] 第{question_num}题 答错了！脚本填='{typed_word}'，屏幕正确答案='{correct_word}'")
    elif status == "wrong":
        log.warning(f"[反馈] 第{question_num}题 答错了（命中'{wrong_hit}'），但没读到正确拼写")
    elif status == "right":
        log.info(f"[反馈] 第{question_num}题 答对了")

    _fb_save_record({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "qn": question_num,
        "typed": typed_word,
        "status": status,
        "correct": correct_word,
        "hit": wrong_hit or right_hit,
        "raw": raw[:600],
    })
    return status, correct_word, raw


def answer_spelling(question_num, word):
    set_english_input()
    click(INPUT_SPELL, 0.1)

    is_intentional_fail = False if DRY_RUN else should_fail(question_num)
    if is_intentional_fail:
        wrong_word = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz',
                                            k=random.randint(max(3, len(word)-2), len(word))))
        log.info(f"[故意答错] 拼写题 #{question_num}: 正确='{word}', 答错='{wrong_word}'")
        _type_word(wrong_word)
        stats["intentional_wrong"] += 1
        stats["total_wrong_answers"] += 1
    else:
        log.info(f"[答题] 拼写题 #{question_num}: '{word}'")
        _type_word(word)
        if not DRY_RUN:
            stats["total_correct_answers"] += 1

    click(BTN_CONFIRM, 0.3)

    # 读一下屏幕上的对错反馈（答错时把正确答案抓回来，后面用它自动纠偏）
    if FB_ENABLED and not is_intentional_fail and not DRY_RUN:
        try:
            st, cw, _raw = read_answer_feedback(question_num, word)
            if st == "wrong" and cw and not FB_PROBE_ONLY:
                # 按题号记住正确答案；一组里每个词只出现一次，不能把它带到下一题
                _RETRY_WORDS[str(question_num)] = cw
                _repair_word_dict(question_num, cw)
        except Exception as e:
            log.debug(f"[反馈] 读取出错(不影响答题): {e}")

    deadline = time.time() + SMART_SPELL_CONFIRM_WAIT
    while time.time() < deadline:
        if stop_flag:
            return
        time.sleep(random.uniform(0.3, 0.5))
        t = ocr_region(REGION_NUMBER)
        m = re.search(r'(\d+)\s*/\s*(\d+)', t)
        if m and int(m.group(1)) + 1 != question_num:
            return
    log.debug("[确认] 题号未及时刷新，继续走下一题流程")

def _ask_user_pick_option(meaning, options):
    """匹配没把握时，请用户自己选一个选项（终端输入或界面输入）"""
    global stop_flag
    print()
    print("  [!] 这道题脚本没把握，需要你来决定")
    print(f"  题目释义: {meaning}")
    log.warning(f"[人工] 脚本没把握，需要你选正确答案。题目释义: {meaning}")
    for i, o in enumerate(options):
        print(f"    {chr(65+i)}: {o}")
        log.warning(f"[人工] 选项{chr(65+i)}: {o}")
    print("  请输入 a / b / c / d （直接回车 = 选 A）")
    ans = _supervised_read_input(
        "选择题没把握：请回 A/B/C/D 选正确答案（直接回车=A，q=终止）")
    if str(ans).strip() == "q":
        log.warning("[人工] 用户选择终止脚本")
        stop_flag = True
        return 0
    pick = {'a': 0, 'b': 1, 'c': 2, 'd': 3}.get(str(ans).strip())
    if pick is not None and pick < len(options):
        log.info(f"[人工] 用户选择 {chr(65+pick)}")
        return pick
    log.warning("[人工] 没收到有效选择，退回 A（无把握）")
    return 0

def answer_choice(question_num, meaning, options):
    for i, opt in enumerate(options):
        log.info(f"  选项{chr(65+i)}: '{opt}'")

    idx, score = fuzzy_option_match(
        meaning, options, threshold=0.0 if DRY_RUN else FUZZY_OPTION_THRESHOLD)

    if idx is None:
        # 第一次没匹配上：重新截一次选项再认一遍（OCR 偶尔抖动）
        log.warning("[匹配] 第一次没匹配上，重截选项再试一次...")
        options2 = []
        for region in REGION_OPTION:
            options2.append(ocr_region(region).strip())
            human_delay(0.1, 0.2)
        log.info(f"[匹配] 重截结果: {options2}")
        idx, score = fuzzy_option_match(meaning, options2 or options)
        if idx is not None:
            options = options2 or options

    if idx is None:
        # 还是没把握：叫用户拍板，绝不偷偷选 A
        idx = _ask_user_pick_option(meaning, options)

    hesitated = False if DRY_RUN else human_hesitate()
    if hesitated:
        log.debug("[犹豫] 已模拟犹豫行为")

    is_intentional_fail = False if DRY_RUN else should_fail(question_num)
    if is_intentional_fail:
        wrong_idx = random.choice([i for i in range(len(OPT_COORDS)) if i != idx])
        log.info(f"[故意答错] 选择题 #{question_num}: 正确={chr(65+idx)}, 答错={chr(65+wrong_idx)}")
        click(OPT_COORDS[wrong_idx])
        stats["intentional_wrong"] += 1
        stats["total_wrong_answers"] += 1
    else:
        log.info(f"[匹配] ✓ {chr(65+idx)} ({score:.2f})")
        click(OPT_COORDS[idx])
        if not DRY_RUN:
            stats["total_correct_answers"] += 1

def test_30_words(word_dict_path=WORD_DICT, start_qn=1, completed_set=None, round_num=1):
    """测试30题，返回完成状态"""
    global stop_flag, screenshot_count
    screenshot_count = 0
    cleanup_screenshots()

    if not os.path.exists(word_dict_path):
        log.error(f"[测试] 词典文件不存在: {word_dict_path}")
        return False
    with open(word_dict_path, 'r', encoding='utf-8') as f:
        word_dict = json.load(f)
    _RETRY_WORDS.clear()

    # 本组 30 个词，给拼写题听音核对用（听出来的词必须在这个名单里才敢用）
    group_words = []
    for _k in sorted(word_dict.keys(), key=lambda z: int(z) if str(z).isdigit() else 0):
        try:
            _v = word_dict[_k]
            _w = _v.get('word', '') if isinstance(_v, dict) else str(_v)
            if _w and str(_w).strip() and str(_w).strip() != '[缺失]':
                group_words.append(str(_w).strip())
        except Exception:
            pass
    log.info(f"[测试] 本组词表 {len(group_words)} 词，供拼写题听音核对")

    completed = set(completed_set or set())
    log.info(f"[测试] 开始测试 30 题，已完成: {sorted(completed)}")
    t0 = time.time()
    op_count = 0
    questions_done = 0

    while True:
        if stop_flag:
            break

        op_count += 1
        log.info(f"\n[操作 #{op_count}] 已完成: {len(completed)}/30")

        # 这里刻意不写题号：start_qn 在正常开新一轮考试时是 1，
        # 写进去会把界面「本组进度」冲回 1/30。
        # 题号统一来自 App 上读到的值，由本题答完后写入
        save_progress(
            round_num=round_num,
            phase="testing",
            test_completed=list(completed)
        )

        log.info("[步骤1] 截取题号...")
        qn = get_question_number()
        log.info(f"[步骤1] 题号={qn}")
        
        if qn == "NOT_TEST_PAGE":
            log.warning("[处理] 当前页面不是测试页面，启动智能导航...")
            success = navigate_to_test(max_attempts=8)
            if success:
                log.info("[处理] 智能导航成功，继续测试")
                human_delay(2, 3)
            else:
                log.error("[处理] 智能导航失败，等待后重试")
                human_delay(3, 5)
            continue
        
        elif qn == "TASK_LIST":
            log.info("[处理] 当前是任务列表页面，启动智能导航...")
            success = navigate_to_test(max_attempts=5)
            if success:
                log.info("[处理] 智能导航成功，继续测试")
                human_delay(2, 3)
            else:
                log.error("[处理] 智能导航失败，等待后重试")
                human_delay(3, 5)
            continue
        
        elif qn is None:
            # OCR 偶发失败（code=101 等）时不要急着导航——先等一等再重读题号，
            # 避免把「识别不出来」误判成「页面不对」而触发耗时的智能导航
            recovered = False
            for attempt in range(1, SMART_QN_NONE_RETRIES + 1):
                if stop_flag:
                    break
                log.info(f"[处理] 题号未识别（第{attempt}/{SMART_QN_NONE_RETRIES}次重试），等待 {SMART_QN_NONE_RETRY_WAIT} 秒后重读...")
                _sleep(SMART_QN_NONE_RETRY_WAIT)
                qn_retry = get_question_number()
                if qn_retry not in (None, "NOT_TEST_PAGE", "TASK_LIST"):
                    log.info(f"[处理] 重试成功，题号={qn_retry}")
                    qn = qn_retry
                    recovered = True
                    break
            if not recovered:
                log.warning("[处理] 多次重读仍无题号，启动智能导航...")
                success = navigate_to_test(max_attempts=5)
                if success:
                    log.info("[处理] 智能导航成功，继续测试")
                    human_delay(2, 3)
                else:
                    log.error("[处理] 智能导航失败，等待后重试")
                    human_delay(3, 5)
                continue

        log.info("[步骤2] 识别题型...")
        qt = determine_question_type(qn)
        log.info(f"[步骤2] 题型={qt}")
        if qt is None:
            human_delay(1.0, 2.0)
            continue

        wi = word_dict.get(str(qn))
        if wi:
            word, meaning = wi.get('word', ''), wi.get('meaning', '')
        else:
            word, meaning = "[缺失]", "[缺失]"

        # 词表里的释义缺失或乱码时，自动去总题库补查一次
        if word and str(word).strip() != "[缺失]":
            _m = str(meaning or "").strip()
            if not _m or _m in ("[缺失]", "[识别失败]"):
                _bank_meaning, _bank_src = lookup_word_meaning(word, None)
                if _bank_meaning:
                    meaning = _bank_meaning
                    log.info(f"[词表] 第{qn}题 '{word}' 释义缺失，已从{_bank_src}补全")
                else:
                    log.warning(f"[词表] 第{qn}题 '{word}' 释义缺失，总题库也查不到")

        # 以屏幕为准：先认出屏幕上真正的单词，再用它查释义（避免词表顺序错位导致答错）
        # 但拼写题是听力题，屏幕上只有输入框没有单词，硬认只会认到助手窗口的文字
        # （吃过亏：把助手界面上的"内置 Rapid"当成了题目单词）
        if qt == '拼写题':
            # 拼写题是听力题，屏幕上没有单词，只能「听」。
            # 两套办法一起准备：①词表顺序候选 ②听音识别结果；两个都拿到再决定填哪个。
            word_by_order = _RETRY_WORDS.get(str(qn), word)
            if str(word_by_order).strip().lower() != str(word).strip().lower():
                log.info(f"[步骤3] 第{qn}题之前答错过，改用屏幕反馈的正确答案 '{word_by_order}'")
                _m2, _src2 = lookup_word_meaning(word_by_order, word_dict)
                if _m2:
                    meaning = _m2
            word = word_by_order

            asr_pick = None
            if SPELLING_SOURCE == "asr":
                asr_pick = try_asr_for_spelling(qn, group_words)
            else:
                log.info("[步骤3] 拼写题：界面选的是「词表顺序」，不听音")

            if asr_pick:
                asr_word, _src = asr_pick
                if str(asr_word).strip().lower() == str(word_by_order).strip().lower():
                    word = asr_word
                    log.info(f"[步骤3] 拼写题双保险一致：听音和词表顺序都是 '{word}'")
                else:
                    word = asr_word
                    log.warning(
                        f"[步骤3] 拼写题听音='{word}'，词表顺序='{word_by_order}'，"
                        f"以听音为准（来源: {_src}）")
                    _m3, _src3 = lookup_word_meaning(word, word_dict)
                    if _m3:
                        meaning = _m3
            else:
                log.warning(f"[步骤3] 拼写题没听出来，退回词表顺序 '{word}'（有错位风险）")
        else:
            sw = ocr_screen_word(word_dict)
            if sw:
                if sw.lower() == str(word).strip().lower():
                    log.info(f"[步骤3] 屏幕单词='{sw}'，与词表一致")
                else:
                    m2, src2 = lookup_word_meaning(sw, word_dict)
                    if m2:
                        log.warning(f"[步骤3] 屏幕单词='{sw}' 与词表'{word}'不一致 → 以屏幕为准（释义来源: {src2}）")
                        word, meaning = sw, m2
                    else:
                        log.warning(f"[步骤3] 屏幕单词='{sw}' 与词表'{word}'不一致，但题库查不到该词 → 沿用词表")
            else:
                log.warning("[步骤3] 没能认出屏幕单词，沿用词表（有错位风险）")
        log.info(f"[步骤3] 单词={word} | 释义={meaning}")

        is_new = qn not in completed
        if is_new:
            completed.add(qn)
            questions_done += 1
            stats["total_questions_answered"] += 1
        log.info(f"[步骤4] {'新题！' if is_new else '重复题'} 题型={qt}")

        read_time = human_read()
        log.info(f"[阅读] 思考 {read_time:.1f} 秒")

        random_break(questions_done)

        if qt == '拼写题':
            # 答案在「步骤3」就已经定好了（听音 / 上一题反馈 / 词表顺序），这里直接填
            answer_spelling(qn, word)
        else:
            log.info("[选项] 逐个截图四个选项...")
            options = []
            for i, region in enumerate(REGION_OPTION):
                save_screenshot(region, qn, f"选项{chr(65+i)}")
                t = ocr_region(region).strip()
                options.append(t)
                log.info(f"  选项{chr(65+i)}: '{t}'")
                human_delay(0.2, 0.5)
            answer_choice(qn, meaning, options)

        if DRY_RUN:
            log.info("[干跑] 已识别第 1 题并算出计划动作，停止（未点击/未输入）")
            stop_flag = True
            break

        reviewed = human_review()
        if reviewed:
            log.debug("[检查] 已模拟检查行为")

        log.info(f"[进度] 题号={qn} | 已完成 {len(completed)}/30")
        # 答完一题就存一次进度，题号以 App 上显示的为准，
        # 这样界面「本组进度」能跟着走（不会一直停在"考试阶段"），
        # 也保证中断时记下的是真实组号而不是本地推算出来的数字
        save_progress(
            round_num=round_num,
            phase="testing",
            test_completed=list(completed),
            test_current_qn=qn,
        )

        if len(completed) >= 30 or qn >= 30:
            log.info("[完成] 已答完30题")
            click(BTN_FINISH, 0.5)
            human_delay(0.5, 1.5)
            click(BTN_BACK, 1)
            human_delay(1.0, 2.0)
            click(BTN_TASK, 5)
            human_delay(0.5, 1.5)
            click(BTN_AGAIN, 0.5)
            break

        click(TEST_NEXT, 0.5)
        _sleep(random.uniform(*SMART_TEST_NEXT_WAIT))

    elapsed = int(time.time() - t0)
    log.info(f"[测试] 完成 {len(completed)} 题，耗时 {format_td(elapsed)}")

    if stop_flag:
        save_progress(
            round_num=round_num,
            phase="testing",
            test_completed=list(completed)
        )

    if DRY_RUN:
        return True
    return len(completed) >= 30


# ================= 校准模式 =================
def finish_calibration_and_save(round_num):
    """第一组完成后，询问是否保存为坐标方案"""
    global calibration_mode, calibration_changes, calibration_renames

    if not calibration_mode:
        return

    log.info("\n[校准] 第一组学习+测试已完成")
    print()
    print("=" * 60)
    print(f"  🎉 第一组（第 {round_num} 组）校准完成")
    print("=" * 60)
    print(f"  校准期间修改的坐标: {len(calibration_changes)} 处")
    print(f"  校准期间重命名的操作: {len(calibration_renames)} 处")
    print("=" * 60)

    if len(calibration_changes) == 0 and len(calibration_renames) == 0:
        print("  本次校准没有修改任何内容")
        ans = monitor_input("是否仍要保存为新方案？(y/n，默认n)", default="n").strip().lower()
        if ans not in ("y", "yes"):
            calibration_mode = False
            calibration_changes.clear()
            calibration_renames.clear()
            log.info("[校准] 校准模式已关闭")
            return

    print()
    profile_name = monitor_input("请输入坐标方案名称（用于保存，下次启动可直接使用）: ").strip()
    if not profile_name:
        profile_name = f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"  未输入名称，使用默认: {profile_name}")

    try:
        from coordinate_profiles import (
            get_current_profile as _gcp, load_profile as _lp,
            save_profile as _sp, build_config_from_profile as _bcp,
            REGION_ITEMS
        )

        current = _gcp()
        existing_data = {}
        if current:
            pdata = _lp(current)
            if pdata:
                existing_data = pdata.get("regions", {})

        new_regions = dict(existing_data)

        print()
        print(f"  📝 将以下修改保存到方案 '{profile_name}':")
        for purpose, (x, y) in calibration_changes.items():
            display_name = calibration_renames.get(purpose, purpose)
            print(f"    - {display_name}: ({x}, {y})")

        for old_name, new_name in calibration_renames.items():
            print(f"    - 重命名: '{old_name}' → '{new_name}'")

        print()
        confirm = monitor_input("确认保存此方案？(y/n，默认y)", default="y").strip().lower()
        if confirm in ("", "y", "yes"):
            new_profile = {
                "name": profile_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "regions": new_regions,
                "calibration_round": round_num,
                "notes": f"第 {round_num} 组校准生成，共修改 {len(calibration_changes)} 处坐标"
            }
            _sp(profile_name, new_profile)
            log.info(f"[校准] 方案已保存: {profile_name}")
            print(f"\n  ✅ 方案 '{profile_name}' 已保存！")
            print(f"  下次启动时可直接使用此方案")

            try:
                from coordinate_profiles import set_current_profile as _scp
                _scp(profile_name)
                log.info(f"[校准] 已设为当前方案: {profile_name}")
            except:
                pass
        else:
            log.info("[校准] 用户取消保存方案")
            print("  已取消保存")

    except Exception as e:
        log.error(f"[校准] 保存方案失败: {e}", exc_info=True)
        print(f"  ❌ 保存失败: {e}")

    calibration_mode = False
    calibration_changes.clear()
    calibration_renames.clear()
    log.info("[校准] 校准模式已关闭")


# ================= 页面状态检测 =================
def detect_current_page():
    """用本地OCR检测当前页面类型，返回 learning/testing/task_list/unknown"""
    try:
        log.debug("[页面检测] 本地OCR检测中...")

        # 注意：「背单词」这个标题在学习页和测试页都会出现，不能单靠它判断测试阶段。
        # 测试页只认它独有的特征：「听写」「请填写你听到的单词」。
        try:
            text_title = ocr_region((1600, 50, 1900, 115))
            log.debug(f"[页面检测] 标题区域: '{text_title}'")
            if ('听写' in text_title) or ('请填写' in text_title):
                log.info("[页面检测] 本地OCR判断: 听写/拼写页面（测试阶段）")
                return "testing"
        except Exception:
            pass

        
        text2 = ocr_region(REGION_NUMBER)
        log.debug(f"[页面检测] 题号区域: '{text2}'")
        
        text = ocr_region(REGION_TODAY)
        log.debug(f"[页面检测] 今日进度区域: '{text}'")
        
        if re.search(r'\d+\s*/\s*\d+', text2):
            if re.search(r'\d+\s*/\s*\d+', text) and ('新' in text or '词' in text):
                pass
            else:
                log.info(f"[页面检测] 本地OCR判断: 测试页面 (题号区域匹配)")
                return "testing"
        
        if re.search(r'\d+\s*/\s*\d+', text) and ('新' in text or '词' in text):
            log.info(f"[页面检测] 本地OCR判断: 学习页面 (今日进度区域匹配)")
            return "learning"
        
        text3 = ocr_region((1400, 200, 1800, 300))
        log.debug(f"[页面检测] 任务区域: '{text3}'")
        if '任务' in text3 or '开始' in text3 or '学习' in text3:
            log.info(f"[页面检测] 本地OCR判断: 任务列表页面")
            return "task_list"
        
        # 恢复阶段可能已经认出页面（例如标题识别到“背单词”），但本次 OCR 又没读到字。
        # 8 秒内有效，避免用到过期结果。
        if _ocr_recovered_page[0] and (time.time() - _ocr_recovered_page[1]) <= 8.0:
            page = _ocr_recovered_page[0]
            _ocr_recovered_page[0] = None
            log.info(f"[页面检测] 采用OCR恢复阶段的判断: {page}")
            return page

        log.info("[页面检测] 本地OCR无法判断，返回 unknown")
        return "unknown"
    except Exception as e:
        log.error(f"[页面检测] 本地OCR异常: {e}")
        return "error"

def safe_navigate_to_learn():
    """安全导航到学习页面"""
    log.info("[导航] 尝试导航到学习页面...")
    for attempt in range(3):
        page = detect_current_page()
        log.debug(f"[导航] 当前页面: {page}")
        if page == "learning":
            return True
        if page == "testing":
            click(BTN_BACK, 1)
            click(BTN_TASK, 3)
            click(BTN_AGAIN, 0.5)
            _sleep(15)
            continue
        if page == "task_list":
            click(BTN_AGAIN, 0.5)
            _sleep(15)
            continue
        click(BTN_BACK, 1)
        click(BTN_TASK, 3)
        click(BTN_AGAIN, 0.5)
        _sleep(15)
    return False


# ================= 主流程 =================
def main():
    global stop_flag, pause_flag

    # ================= 自动更新检查（最优先） =================
    try:
        from auto_updater import check_and_ask_update
        update_result = check_and_ask_update(force_check=False)
        if update_result == "updating":
            # 更新脚本已启动，主程序必须立即退出，否则 exe 被占用无法覆盖
            log.info("[更新] 已启动更新程序，主程序退出")
            print("\n  更新程序已启动，3 秒后关闭主程序...\n")
            time.sleep(3)
            sys.exit(0)
    except Exception as _e:
        log.warning(f"[更新] 检查模块异常（不影响使用）: {_e}")
        print(f"[更新] 检查模块异常（不影响使用）: {_e}\n")

    log.info("=" * 60)
    log.info(f"  OneClass 刷单词脚本（增强版）启动")
    log.info(f"  北京时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)
    log.info(f"  项目目录: {BASE_DIR}")
    # 输出版本号
    try:
        from auto_updater import load_app_version
        _av = load_app_version()
        log.info(f"  版本号: v{_av.get('version', '未知')}")
    except Exception:
        pass
    log.info(f"  OCR 地址: {UMI_OCR_URL}")
    log.info(f"  每组词数: {GROUP_SIZE}")
    log.info(f"  错误率: {FAIL_RATE*100:.0f}%")
    log.info(f"  组间休息: {'开启' if REST_ENABLED else '关闭'} ({REST_MIN}-{REST_MAX}秒)")
    log.info(f"  随机休息: {'开启' if RANDOM_BREAK_ENABLED else '关闭'}")
    log.info(f"  曲线鼠标: {'开启' if MOUSE_CURVE else '关闭'}")
    log.info("=" * 60)

    load_stats()
    stats["start_time"] = datetime.now().isoformat()
    global _session_snapshot
    _session_snapshot = dict(stats)  # 保存本次运行前的统计快照

    start_hotkey_listeners()

    if not init_umi():
        log.error("[启动] OCR 初始化失败，退出")
        return


    # ================= 坐标方案加载 =================
    log.info("\n[启动] 加载坐标方案...")
    has_saved_profile = False
    try:
        from coordinate_profiles import get_current_profile as _gcp, load_profile as _lp, build_config_from_profile as _bcp
        cprof = _gcp()
        if cprof:
            pdata = _lp(cprof)
            if pdata:
                coord_config = _bcp(pdata)
                apply_coord_profile(coord_config)
                CONFIG["regions"] = coord_config
                has_saved_profile = True
                log.info(f"[坐标] 已加载方案: {cprof}")
            else:
                log.warning("[坐标] 方案数据为空，使用默认坐标")
        else:
            log.info("[坐标] 无保存的方案，将使用默认坐标")
    except Exception as e:
        log.warning(f"[坐标] 加载失败: {e}，使用默认坐标")

    # ================= 词典检测与题库加载 =================
    log.info("\n[启动] 检测词典...")
    
    dict_name = detect_dictionary_name()
    log.info(f"[词典] 当前词典: '{dict_name}'")

    # 开启本次运行的词典归档（词记录会写入 题库/运行记录/）
    run_record_start(dict_name)

    dict_bank_data = load_dictionary_bank(dict_name)
    bank_word_count = len(dict_bank_data.get("words", []))
    bank_confirmed = dict_bank_data.get("confirmed", False)
    bank_expected = dict_bank_data.get("expected_total", 2862)
    
    if bank_word_count > 0:
        if bank_confirmed:
            log.info(f"[题库] '{dict_name}' 题库已确认完整: {bank_word_count}/{bank_expected} 词")
    else:
        log.info(f"[题库] '{dict_name}' 暂无题库")
        if dict_name != "默认词汇表" and has_bank_for_dict("默认词汇表"):
            migrated = try_migrate_default_bank(dict_name, monitor_input)
            if migrated:
                dict_bank_data = load_dictionary_bank(dict_name)
                bank_word_count = len(dict_bank_data.get("words", []))
                bank_confirmed = dict_bank_data.get("confirmed", False)
                bank_expected = dict_bank_data.get("expected_total", 2862)
                log.info(f"[题库] 迁移后: {bank_word_count}/{bank_expected} 词")

    # 把该词典已收录的词导出到「题库」文件夹：词典_xxx.json / 词典_xxx.txt
    export_dictionary_snapshot(dict_name, dict_bank_data, reason="启动时导出")

    # 逐词精简模式状态提示
    _bank_total = len((dict_bank_data or {}).get("words", []))
    _bank_confirmed = count_confirmed_words(dict_bank_data)
    if is_word_skip_enabled(dict_bank_data) and _bank_confirmed > 0:
        log.info(f"[精简] 词典 '{dict_name}'：册内已确定的 {_bank_confirmed}/{_bank_total} 词将跳过截图/OCR，其余词仍走OCR识别+纠错")
    elif is_word_skip_enabled(dict_bank_data):
        log.info(f"[精简] 词典 '{dict_name}'：册内 {_bank_total} 词全部为「未确定」→ 本组全走OCR识别，识别后入库")
    elif SMART_ENABLED:
        log.info(f"[精简] 未启用（词典库为空或精简开关关闭）")
    if is_bank_trusted(dict_bank_data):
        log.info(f"[精简] 整本词典已确认 → 同时启用等待精简，进度OCR每{SMART_PROGRESS_OCR_EVERY_N}词一次")

    # ================= OCR实时检测页面状态 =================
    detected_page_type = "unknown"
    app_progress_read = False   # App 是否明确读到了「x/总数」进度
    detected_is_word_test = False
    ocr_global_done = 0
    ocr_round = 0
    ocr_learn_start_global = 0
    ocr_learn_start_local = 0
    ocr_progress_text = ""
    ocr_today_text = ""

    log.info("\n[启动] 本地OCR检测页面状态...")
    ocr_page = detect_current_page()
    if ocr_page in ["learning", "testing", "task_list"]:
        detected_page_type = ocr_page
        detected_is_word_test = True
        log.info(f"[启动] 本地OCR检测页面类型: {detected_page_type}")
    else:
        log.warning(f"[启动] 本地OCR检测失败 ({ocr_page})，尝试自动恢复...")
        if not auto_recover(f"启动时无法识别页面类型({ocr_page})", phase="startup", attempts=3):
            log.error("[启动] 自动恢复失败，脚本停止")
            stop_flag = True
            return
        detected_page_type = detect_current_page()
        if detected_page_type in ["learning", "testing"]:
            detected_is_word_test = True

    # OCR识别总进度
    if detected_page_type in ["learning", "testing"]:
        try:
            if detected_page_type == "learning":
                ocr_progress_text = ocr_region(REGION_WORD_INDEX)
                log.debug(f"[启动] 进度区域OCR: '{ocr_progress_text}'")
                ocr_today_text = ocr_region(REGION_TODAY)
                log.debug(f"[启动] 今日新词区域OCR: '{ocr_today_text}'")

                ocr_global_done, _ = _parse_slash_progress(ocr_progress_text)
                if ocr_global_done > 0:
                    log.info(f"[启动] 进度区域识别: 已完成 {ocr_global_done} 词")

                today_current = 0
                today_total = 0
                today_current, today_total = _parse_slash_progress(ocr_today_text)
                if today_current > 0 and today_total > 0:
                    log.info(f"[启动] 今日新词区域识别: 当前 {today_current}/{today_total}")

                if ocr_global_done > 0 and today_current > 0 and today_total > 0:
                    # 用户公式: offset_in_group = GROUP_SIZE - (today_total - today_current) + 1
                    offset_in_group = GROUP_SIZE - (today_total - today_current) + 1
                    ocr_global_done = ocr_global_done + offset_in_group - 1
                    log.info(f"[启动] 进度 {ocr_global_done + 1 - offset_in_group} + 组内偏移 {offset_in_group} = 已完成 {ocr_global_done} 词")
            else:
                # 考试阶段同样以 App 显示的进度为准（和上面学习页一个规矩）：
                # 考试弹窗打开时，左侧主页的「进度 X/Y」仍然可见，先读它；
                # 读不到（App 被挡住、最小化、坐标偏了）才退回本地统计推算
                try:
                    test_prog_text = ocr_region(REGION_WORD_INDEX)
                    log.debug(f"[启动] 考试阶段进度区域OCR: '{test_prog_text}'")
                    test_done, _t = _parse_slash_progress(test_prog_text)
                    if _t > 0:
                        # 只要读到了「x/总数」，就以 App 为准，哪怕 x 是 0（新一轮）
                        app_progress_read = True
                        ocr_global_done = max(0, test_done)
                        log.info(f"[启动] 考试阶段按App显示进度: 已完成 {test_done} 词（总数 {_t}）")
                except Exception as e:
                    log.debug(f"[启动] 考试阶段读App进度失败: {e}")
                if not app_progress_read and ocr_global_done <= 0:
                    if stats.get("total_words_learned", 0) >= bank_word_count and stats["total_words_learned"] > 0:
                        ocr_global_done = stats["total_words_learned"]
                    elif bank_word_count > 0:
                        ocr_global_done = ((bank_word_count - 1) // GROUP_SIZE) * GROUP_SIZE

            if ocr_global_done > 0:
                ocr_round = (ocr_global_done // GROUP_SIZE) + 1
                log.info(f"[启动] 推算：已完成 {ocr_global_done} 词，当前第 {ocr_round} 组")

                if detected_page_type == "learning":
                    ocr_learn_start_global = ocr_global_done + 1
                    ocr_learn_start_local = ((ocr_global_done) % GROUP_SIZE) + 1
        except Exception as e:
            log.warning(f"[启动] 进度推算失败: {e}")

    # 构建OCR检测信息
    ocr_info = {
        'page_type': detected_page_type,
        'app_progress_read': app_progress_read,
        'progress_text': ocr_progress_text,
        'today_text': ocr_today_text,
        'ocr_global_done': ocr_global_done,
        'ocr_round': ocr_round,
        'learn_local': ocr_learn_start_local,
        'learn_global': ocr_learn_start_global,
    }

    # ================= 读取上次进度 + 确认 =================
    prog = load_progress()
    resume, prog_data = ask_resume_progress(prog, ocr_info)

    round_num = 1
    initial_phase = None
    learn_start_local = 1
    learn_start_global = 1
    partial_dict = None
    partial_bank = None
    test_completed = None
    is_first_round = True

    if resume and prog_data:
        # 优先使用OCR检测的位置，OCR失败时回退到progress.json
        if ocr_round > 0:
            round_num = ocr_round
        else:
            round_num = prog_data.get("round_num", 1)

        if detected_page_type in ["learning", "testing"]:
            initial_phase = detected_page_type
        else:
            initial_phase = prog_data.get("phase", "learning")

        is_first_round = False

        # 统计数据同步修正
        if round_num - 1 > stats.get("total_rounds", 0):
            old_stat = stats.get("total_rounds", 0)
            stats["total_rounds"] = round_num - 1
            log.info(f"[统计] 同步修正: {old_stat} → {stats['total_rounds']} 组（与进度对齐）")
        stats["total_rounds"] = max(stats["total_rounds"], round_num - 1)

        prog_dict_name = prog_data.get("dict_name", dict_name)
        if prog_dict_name != dict_name:
            log.warning(f"[恢复] 进度文件词典 '{prog_dict_name}' 与当前 '{dict_name}' 不一致")

        if initial_phase == "learning":
            if ocr_learn_start_global > 0:
                learn_start_local = ocr_learn_start_local
                learn_start_global = ocr_learn_start_global
                log.info(f"[恢复] 使用OCR位置: 本组第{learn_start_local}词 / 词典第{learn_start_global}词")
            else:
                learn_start_local = prog_data.get("learn_local_index", 1)
                learn_start_global = prog_data.get("learn_global_index", 1)
                log.info(f"[恢复] 使用进度文件位置: 本组第{learn_start_local}词 / 词典第{learn_start_global}词")
            partial_dict = prog_data.get("word_dict", {})
            partial_bank = prog_data.get("bank_dict", {})
        elif initial_phase == "testing":
            test_completed = prog_data.get("test_completed", [])
    else:
        clear_progress()
        # 不恢复时，也使用OCR检测到的位置
        if ocr_round > 0:
            round_num = ocr_round
            learn_start_global = ocr_learn_start_global
            learn_start_local = ocr_learn_start_local
        # 页面类型必须无条件设置：即使没推算到组号，只要检测出是测试页，
        # 就不能再进学习阶段，否则会按学习页坐标乱点。
        if detected_page_type in ["learning", "testing"]:
            initial_phase = detected_page_type

    # ================= 校准模式判断 =================
    global calibration_mode
    if is_first_round and not has_saved_profile:
        calibration_mode = True
        log.info("\n[校准] 检测到是第一组且无保存的坐标方案")
        log.info("[校准] 开启校准模式 - 第一组每步操作前将详细说明并等待确认")
        print()
        print("=" * 60)
        print("  📐 校准模式已开启")
        print("=" * 60)
        print("  第一组单词运行时，每步操作都会详细说明并等待确认")
        print("  你可以随时校准坐标、修改操作名称")
        print("  第一组完成后可保存为坐标方案，以后直接使用")
        print("=" * 60)
        input("\n  按 Enter 开始第一组校准...")
    elif is_first_round and has_saved_profile:
        ans = monitor_input("是否开启校准模式验证第一组？(y/n，默认n)", default="n").strip().lower()
        if ans in ("y", "yes"):
            calibration_mode = True
            log.info("[校准] 用户选择开启校准模式")
            print("  📐 校准模式已开启")
        else:
            log.info("[启动] 使用已有坐标方案，跳过校准")

    # 测试页面：以 App 显示的数字为准。它表示“已完成几题”，不是“当前第几题”。
    # 例：显示 29/30 = 已完成29题，当前第30题。
    if detected_page_type == "testing":
        try:
            qn_text = ocr_region(REGION_NUMBER)
            log.debug(f"[启动] 题号区域OCR: '{qn_text}'")
            m = re.search(r'(\d+)\s*/\s*(\d+)', qn_text)
            if m:
                done_count = int(m.group(1))
                expected = list(range(1, done_count + 1))
                saved = test_completed or []
                if not saved or set(saved) != set(expected):
                    if saved:
                        log.warning(
                            f"[启动] 保存进度({len(saved)}题)与App显示({done_count}题)不一致，按App进度校准")
                    test_completed = expected
                    log.info(f"[启动] OCR识别当前第 {done_count + 1} 题，自动恢复前 {done_count} 题进度")
        except Exception as e:
            log.warning(f"[启动] 题号OCR解析失败: {e}")

    if bank_confirmed and bank_word_count >= bank_expected:
        log.info(f"[启动] 题库已确认完整，跳过学习阶段，直接进入测试")
        initial_phase = "testing"
        test_completed = []
        learn_start_local = 1
        learn_start_global = 1
        partial_dict = {}
        partial_bank = {}
    else:
        if detected_page_type == "testing":
            log.info("[启动] 检测到当前是测试页面")
            if test_completed is None:
                log.info("[启动] 无已保存的测试进度，从头开始测试")
                test_completed = []
            else:
                log.info(f"[启动] 恢复测试进度，已完成: {len(test_completed)} 题")
        elif detected_page_type in ["news", "task_list", "login", "unknown"] and not calibration_mode:
            if detected_is_word_test:
                log.info(f"[启动] 当前在{detected_page_type}页面但属于单词应用，尝试导航")
                navigate_to_test(max_attempts=4)
            else:
                log.warning(f"[启动] 当前在非单词页面({detected_page_type})，尝试自动恢复...")
                if not auto_recover(f"当前在非单词页面: {detected_page_type}", phase="startup", attempts=3):
                    log.error("[启动] 自动恢复失败，脚本停止")
                    stop_flag = True

    stats["total_rounds"] = max(stats["total_rounds"], round_num - 1)

    while not stop_flag:
        log.info(f"\n{'='*50}\n  第 {round_num} 组\n{'='*50}")
        stats["total_rounds"] = max(stats["total_rounds"], round_num)

        if initial_phase in (None, "learning") or round_num > stats.get("total_rounds", 1):
            log.info(f"\n--- 阶段1：学习 {GROUP_SIZE} 词 ---")
            try:
                # 判断起始位置：
                # - 从进度恢复（且阶段匹配）：用进度文件的精确位置（可能做到一半）
                # - 新开始/不恢复：用OCR推算的位置（若OCR失败则默认第1词，learn_30_words内部会自修正）
                if resume and initial_phase == "learning" and prog_data and round_num == prog_data.get("round_num", round_num):
                    start_local = learn_start_local
                    start_global = learn_start_global
                    use_partial_dict = partial_dict
                    use_partial_bank = partial_bank
                else:
                    start_local = learn_start_local  # OCR推算的组内位置（默认1，learn_30_words内部会自修正）
                    start_global = learn_start_global  # OCR推算的全局位置
                    use_partial_dict = None
                    use_partial_bank = None
                
                wd, bank, updated_bank = learn_30_words(
                    first_round=(round_num == 1 and not resume),
                    start_local_idx=start_local,
                    start_global_idx=start_global,
                    partial_dict=use_partial_dict,
                    partial_bank=use_partial_bank,
                    dict_name=dict_name,
                    dict_bank_data=dict_bank_data,
                    round_num=round_num
                )
            except Exception as e:
                log.error(f"[学习] 异常: {e}", exc_info=True)
                save_stats()
                save_progress(round_num=round_num, phase="learning", dict_name=dict_name)
                if not auto_recover(f"学习阶段异常: {e}", phase="learning", attempts=3):
                    break
                human_delay(3, 5)
                continue

            if wd is None:
                log.warning("[主流程] 学习阶段被中断（详细进度已由learn_30_words保存）")
                if not auto_recover("学习阶段被中断", phase="learning", attempts=3):
                    break
                human_delay(3, 5)
                continue

            # 如果返回空词典，说明当前已是测试页面，跳过学习
            if len(wd) == 0:
                log.info("[主流程] 跳过学习，直接进入测试")
                initial_phase = "testing"
                test_completed = []
            else:
                # 正常学习完成
                with open(WORD_DICT, 'w', encoding='utf-8') as f:
                    json.dump(wd, f, indent=2, ensure_ascii=False)
                log.info(f"[完成] 本轮词典已保存: {WORD_DICT}")

                # 保存按词典分类的题库
                if updated_bank:
                    dict_bank_data = updated_bank
                    save_dictionary_bank(dict_name, dict_bank_data)
                    bank_count = len(dict_bank_data.get("words", []))
                    expected = dict_bank_data.get("expected_total", 2862)
                    log.info(f"[完成] 词典题库已保存: '{dict_name}' {bank_count}/{expected} 词")

                # 归档：本组识别的词写进「题库/运行记录」，并刷新词典导出文件
                run_record_collect(bank, only_global=True)
                export_dictionary_snapshot(dict_name, dict_bank_data, reason="学习完成后导出")
                run_record_save("学习完成")

                initial_phase = None
                partial_dict = None
                partial_bank = None

                test_wait = SMART_FINISH_WAIT + 2.5
                log.info(f"[等待] {test_wait:.1f}秒后开始测试...")
                _sleep(test_wait)
                set_english_input()

        log.info(f"\n--- 阶段2：测试 {GROUP_SIZE} 题 ---")
        
        # 再次检测页面状态，确保当前确实是测试页面
        actual_page = detect_current_page()
        if actual_page == "learning":
            log.warning(f"[主流程] OCR检测到当前是学习页面，但进度记录为测试阶段")
            log.warning(f"[主流程] 重新进入学习阶段...")
            initial_phase = "learning"
            round_num -= 1
            continue
        elif actual_page in ["task_list", "unknown"]:
            log.warning(f"[主流程] OCR检测到当前是{actual_page}页面，尝试导航到测试页面")
            if not navigate_to_test(max_attempts=5):
                log.error("[主流程] 导航到测试页面失败")
                if not auto_recover(f"无法从{actual_page}页面进入测试", phase="testing", attempts=3):
                    break
                continue
        
        try:
            if initial_phase == "testing" and test_completed is not None:
                success = test_30_words(completed_set=set(test_completed), round_num=round_num)
                initial_phase = None
                test_completed = None
            else:
                success = test_30_words(round_num=round_num)
        except Exception as e:
            log.error(f"[测试] 异常: {e}", exc_info=True)
            save_stats()
            save_progress(round_num=round_num, phase="testing", dict_name=dict_name)
            if not auto_recover(f"测试阶段异常: {e}", phase="testing", attempts=3):
                break
            human_delay(3, 5)
            continue

        if not success:
            log.warning("[主流程] 测试阶段未完成或被中断（详细进度已由test_30_words保存）")
            if not auto_recover("测试阶段未完成或被中断", phase="testing", attempts=3):
                break
            human_delay(3, 5)
            continue

        stats["total_rounds"] = round_num
        save_stats()

        if stop_flag:
            break

        if calibration_mode:
            finish_calibration_and_save(round_num)

        print_stats_summary()

        if REST_ENABLED:
            rest_between_rounds()

        round_num += 1
        save_progress(round_num=round_num, phase="round_start", dict_name=dict_name)

    log.info("\n[结束] 脚本已停止")
    save_stats()
    print_stats_summary()

    # 脚本结束时检查题库是否达到预期总数，提示用户确认
    if dict_bank_data and not dict_bank_data.get("confirmed", False):
        bank_count = len(dict_bank_data.get("words", []))
        expected = dict_bank_data.get("expected_total", 2862)
        if bank_count >= expected:
            log.info(f"[题库] 当前题库 '{dict_name}' 已收录 {bank_count}/{expected} 词，达到预期总数")
            if SMART_AUTO_CONFIRM_BANK:
                # 整本确认：同时把每个词也标成「已确定」，保证逐词判定一致
                for _w in dict_bank_data.get("words", []):
                    _w["confirmed"] = True
                dict_bank_data["confirmed"] = True
                save_dictionary_bank(dict_name, dict_bank_data)
                export_dictionary_snapshot(dict_name, dict_bank_data, reason="录满自动确认")
                log.info(f"[题库] '{dict_name}' 已录满，自动确认为正式题库（{bank_count} 词全部标为已确定）")
                print()
                print("=" * 50)
                print(f"  题库 '{dict_name}' 已录满 {bank_count} 词，已自动确认")
                print(f"  下次刷这本词典：册内已收录的词自动跳过截图/OCR（逐词精简）")
                print("=" * 50)
            else:
                print()
                print("=" * 50)
                print(f"  题库 '{dict_name}' 已收录 {bank_count} 词")
                print(f"  是否确认为正式题库？确认后将跳过OCR直接使用题库")
                print("=" * 50)
                ans = monitor_input("确认题库？(y/n，默认n)", default="n").strip().lower()
                if ans in ('y', 'yes'):
                    for _w in dict_bank_data.get("words", []):
                        _w["confirmed"] = True
                    dict_bank_data["confirmed"] = True
                    save_dictionary_bank(dict_name, dict_bank_data)
                    export_dictionary_snapshot(dict_name, dict_bank_data, reason="题库已确认")
                    log.info(f"[题库] '{dict_name}' 已确认为正式题库（{bank_count} 词全部标为已确定）")
                    print(f"  已确认！下次刷该词典将跳过OCR，直接使用题库")
                else:
                    log.info(f"[题库] 用户未确认，题库保持未确认状态")
                    print(f"  未确认，下次仍将进行OCR验证/补全")
        else:
            log.info(f"[题库] 当前题库 '{dict_name}' 已收录 {bank_count}/{expected} 词，尚未达到预期总数")

    # ================= 词典归档 & 导出（脚本结束） =================
    try:
        run_record_collect_from_progress()   # 兜底：把中断进度里的词补捞进来
        if dict_bank_data:
            export_dictionary_snapshot(dict_name, dict_bank_data, reason="脚本结束时导出")
        run_record_finish("脚本结束")
    except Exception as _arc_e:
        log.warning(f"[归档] 结束时归档失败（不影响使用）: {_arc_e}")

    runtime = int(time.time() - _start_time)
    log.info(f"  总运行时间: {format_td(runtime)}")
    log.info(f"  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  日志文件: {LOG_DIR}")
    log.info(f"  统计文件: {STATS_PATH}")
    log.info("=" * 60)


def on_error(exc):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    screenshot_path = LOG_DIR / f"error_{timestamp}.png"
    log_path = LOG_DIR / f"error_{timestamp}.txt"

    try:
        ImageGrab.grab().save(screenshot_path)
        log.error(f"[崩溃] 已保存全屏截图: {screenshot_path}")
    except Exception as e:
        log.error(f"[崩溃] 截图失败: {e}")

    try:
        import traceback
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"发生时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"错误类型: {type(exc).__name__}\n")
            f.write(f"错误信息: {str(exc)}\n")
            f.write("\n完整堆栈:\n")
            f.write(traceback.format_exc())
        log.error(f"[崩溃] 已保存错误日志: {log_path}")
    except Exception as e:
        log.error(f"[崩溃] 保存日志失败: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("[中断] 键盘中断")
        log.info(f"  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        save_stats()
        try:
            run_record_finish("键盘中断")
        except Exception:
            pass
    except Exception as e:
        log.critical(f"[崩溃] 未捕获异常: {e}", exc_info=True)
        on_error(e)
        save_stats()
        try:
            run_record_finish("异常退出")
        except Exception:
            pass
        # 自动恢复：重新启动主流程一次，第二次还崩就退出
        log.warning("[崩溃] 3 秒后自动重启主流程一次...")
        time.sleep(3)
        try:
            main()
        except Exception as e2:
            log.critical(f"[崩溃] 自动重启后再次异常，无法继续: {e2}", exc_info=True)
            on_error(e2)
            save_stats()
            log.error("[崩溃] 脚本已停止，请查看 logs/ 目录")
