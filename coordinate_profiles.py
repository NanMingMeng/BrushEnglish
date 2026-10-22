#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坐标方案管理模块
=================
功能：
- 交互式校准所有 OCR 区域和按钮坐标
- 截图预览验证（直观看到区域是否正确）
- OCR 识别结果实时显示
- 鼠标定位 + 手动输入两种校准方式
- 多方案管理（保存/加载/切换）
- 本地 OCR 为主，AI 为辅
"""

import os
import io
import json
import time
import base64
import urllib.request
import pyautogui
from PIL import Image, ImageGrab
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "coordinate_profiles"
PROFILE_DIR.mkdir(exist_ok=True)
PREVIEW_DIR = BASE_DIR / "coordinate_previews"
PREVIEW_DIR.mkdir(exist_ok=True)
CURRENT_PROFILE_FILE = BASE_DIR / "current_profile.json"

UMI_OCR_URL = "http://127.0.0.1:1224/api/ocr"

# ================= 坐标项定义 =================
COORD_ITEMS = [
    {
        "key": "learn_word",
        "name": "学习页面 - 单词区域",
        "desc": "学习页面显示英文单词的区域",
        "type": "rect",
        "default": [1467, 188, 1799, 290],
        "path": ["learn", "word"]
    },
    {
        "key": "learn_meaning",
        "name": "学习页面 - 释义区域",
        "desc": "学习页面显示中文释义的区域",
        "type": "rect",
        "default": [1480, 399, 1914, 596],
        "path": ["learn", "meaning"]
    },
    {
        "key": "learn_today",
        "name": "学习页面 - 进度区域",
        "desc": "学习页面显示今日进度 x/30 的区域",
        "type": "rect",
        "default": [1632, 95, 1735, 160],
        "path": ["learn", "today"]
    },
    {
        "key": "learn_dict_name",
        "name": "学习页面 - 词典名称区域",
        "desc": "学习页面显示词典/词汇表名称的区域",
        "type": "rect",
        "default": [1480, 130, 1914, 180],
        "path": ["learn", "dict_name"]
    },
    {
        "key": "learn_word_index",
        "name": "学习页面 - 单词序号区域",
        "desc": "学习页面显示单词序号 x/30 的区域",
        "type": "rect",
        "default": [1294, 371, 1400, 410],
        "path": ["learn", "word_index"]
    },
    {
        "key": "learn_btn_view",
        "name": "学习页面 - 查看释义按钮",
        "desc": "学习页面点击查看释义的按钮",
        "type": "point",
        "default": [1675, 432],
        "path": ["learn", "btn_view"]
    },
    {
        "key": "learn_btn_easy",
        "name": "学习页面 - 太简单按钮",
        "desc": "学习页面标记太简单的按钮",
        "type": "point",
        "default": [1846, 210],
        "path": ["learn", "btn_easy"]
    },
    {
        "key": "learn_next",
        "name": "学习页面 - 下一个按钮",
        "desc": "学习页面进入下一个单词的按钮",
        "type": "point",
        "default": [1679, 943],
        "path": ["learn", "learn_next"]
    },
    {
        "key": "test_number",
        "name": "测试页面 - 题目号区域",
        "desc": "测试页面显示第几题 x/30 的区域",
        "type": "rect",
        "default": [1457, 99, 1616, 134],
        "path": ["test", "number"]
    },
    {
        "key": "test_question_type",
        "name": "测试页面 - 题型区域",
        "desc": "测试页面显示题目类型（拼写/选择）的区域",
        "type": "rect",
        "default": [1463, 167, 1632, 200],
        "path": ["test", "question_type"]
    },
    {
        "key": "test_option_1",
        "name": "测试页面 - 选项1区域",
        "desc": "测试页面第1个选项的OCR识别区域",
        "type": "rect",
        "default": [1465, 388, 1895, 440],
        "path": ["test", "option_regions", 0]
    },
    {
        "key": "test_option_2",
        "name": "测试页面 - 选项2区域",
        "desc": "测试页面第2个选项的OCR识别区域",
        "type": "rect",
        "default": [1465, 468, 1895, 520],
        "path": ["test", "option_regions", 1]
    },
    {
        "key": "test_option_3",
        "name": "测试页面 - 选项3区域",
        "desc": "测试页面第3个选项的OCR识别区域",
        "type": "rect",
        "default": [1465, 545, 1895, 597],
        "path": ["test", "option_regions", 2]
    },
    {
        "key": "test_option_4",
        "name": "测试页面 - 选项4区域",
        "desc": "测试页面第4个选项的OCR识别区域",
        "type": "rect",
        "default": [1465, 619, 1895, 671],
        "path": ["test", "option_regions", 3]
    },
    {
        "key": "test_input_spell",
        "name": "测试页面 - 拼写输入框",
        "desc": "测试页面拼写题的输入框位置",
        "type": "point",
        "default": [1675, 378],
        "path": ["test", "input_spell"]
    },
    {
        "key": "test_btn_speaker_replay",
        "name": "测试页面 - 重播读音按钮（喇叭）",
        "desc": "拼写题界面上那个小喇叭图标，点一下会重新读一遍单词。\n"
                "只在「拼写题答案来源 = 听音识别」且第一次没听准时才用得到。\n"
                "默认坐标是猜的，请在你自己的拼写题界面校准成真实位置。",
        "type": "point",
        "default": [1675, 340],
        "path": ["test", "btn_speaker_replay"]
    },
    {
        "key": "test_btn_confirm",
        "name": "测试页面 - 确认按钮",
        "desc": "测试页面确认答案的按钮",
        "type": "point",
        "default": [1680, 465],
        "path": ["test", "btn_confirm"]
    },
    {
        "key": "test_next",
        "name": "测试页面 - 下一题按钮",
        "desc": "测试页面进入下一题的按钮",
        "type": "point",
        "default": [1679, 980],
        "path": ["test", "test_next"]
    },
    {
        "key": "test_btn_finish",
        "name": "测试页面 - 完成按钮",
        "desc": "测试页面完成测试的按钮",
        "type": "point",
        "default": [1670, 980],
        "path": ["test", "btn_finish"]
    },
    {
        "key": "test_btn_back",
        "name": "测试页面 - 返回按钮",
        "desc": "测试页面左上角返回按钮",
        "type": "point",
        "default": [1470, 50],
        "path": ["test", "btn_back"]
    },
    {
        "key": "test_btn_task",
        "name": "测试页面 - 任务按钮",
        "desc": "测试页面跳转任务列表的按钮",
        "type": "point",
        "default": [1055, 400],
        "path": ["test", "btn_task"]
    },
    {
        "key": "test_btn_again",
        "name": "测试页面 - 再来一组按钮",
        "desc": "结果页面再来一组的按钮",
        "type": "point",
        "default": [1800, 960],
        "path": ["test", "btn_again"]
    },
    {
        "key": "test_opt_1",
        "name": "测试页面 - 选项1点击位置",
        "desc": "测试页面点击第1个选项的位置",
        "type": "point",
        "default": [1680, 420],
        "path": ["test", "option_coords", 0]
    },
    {
        "key": "test_opt_2",
        "name": "测试页面 - 选项2点击位置",
        "desc": "测试页面点击第2个选项的位置",
        "type": "point",
        "default": [1680, 500],
        "path": ["test", "option_coords", 1]
    },
    {
        "key": "test_opt_3",
        "name": "测试页面 - 选项3点击位置",
        "desc": "测试页面点击第3个选项的位置",
        "type": "point",
        "default": [1680, 580],
        "path": ["test", "option_coords", 2]
    },
    {
        "key": "test_opt_4",
        "name": "测试页面 - 选项4点击位置",
        "desc": "测试页面点击第4个选项的位置",
        "type": "point",
        "default": [1680, 650],
        "path": ["test", "option_coords", 3]
    },
]


def get_profile_path(profile_name):
    safe_name = profile_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return PROFILE_DIR / f"profile_{safe_name}.json"


def list_profiles():
    profiles = []
    for f in PROFILE_DIR.glob("profile_*.json"):
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                name = data.get("name", f.stem.replace("profile_", ""))
                profiles.append({"name": name, "file": f.name})
        except:
            pass
    return profiles


def load_profile(profile_name):
    profile_path = get_profile_path(profile_name)
    if not profile_path.exists():
        return None
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[坐标方案] 加载方案失败: {e}")
        return None


def save_profile(profile_name, coord_data):
    profile_path = get_profile_path(profile_name)
    data = {
        "name": profile_name,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "regions": coord_data
    }
    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[坐标方案] 保存方案失败: {e}")
        return False


def get_current_profile():
    if CURRENT_PROFILE_FILE.exists():
        try:
            with open(CURRENT_PROFILE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("current_profile", "")
        except:
            pass
    return ""


def set_current_profile(profile_name):
    try:
        with open(CURRENT_PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump({"current_profile": profile_name}, f)
        return True
    except:
        return False


def get_mouse_position():
    pos = pyautogui.position()
    return pos.x, pos.y


def wait_and_capture(prompt="将鼠标移动到目标位置，3秒后自动记录"):
    print(f"\n  {prompt}")
    for i in range(3, 0, -1):
        print(f"  {i}...", end="", flush=True)
        time.sleep(1)
    x, y = get_mouse_position()
    print(f"  已记录: ({x}, {y})")
    return x, y


def ocr_region_by_coord(left, top, right, bottom):
    try:
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_bytes = img_byte_arr.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        data = json.dumps({"base64": img_b64}).encode('utf-8')
        req = urllib.request.Request(
            UMI_OCR_URL,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        if result.get("code") == 100:
            texts = []
            for item in result.get("data", []):
                texts.append(item.get("text", ""))
            return "\n".join(texts)
        return ""
    except Exception as e:
        return f"[OCR失败: {e}]"


def capture_preview_rect(region, item_key):
    left, top, right, bottom = region
    try:
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
        preview_path = PREVIEW_DIR / f"preview_{item_key}_{int(time.time())}.png"
        screenshot.save(str(preview_path))
        return str(preview_path)
    except Exception as e:
        print(f"  [预览] 截图失败: {e}")
        return None


def capture_preview_point(x, y, item_key, size=100):
    try:
        half = size // 2
        left = max(0, x - half)
        top = max(0, y - half)
        right = left + size
        bottom = top + size
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
        preview_path = PREVIEW_DIR / f"preview_{item_key}_{int(time.time())}.png"
        screenshot.save(str(preview_path))
        return str(preview_path)
    except Exception as e:
        print(f"  [预览] 截图失败: {e}")
        return None


def open_preview_image(image_path):
    if not image_path or not os.path.exists(image_path):
        return
    try:
        os.startfile(image_path)
    except Exception as e:
        print(f"  [预览] 打开图片失败: {e}")


def delete_preview(image_path):
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
        except:
            pass


def manual_input_point():
    print("\n  请手动输入坐标，格式: x,y")
    while True:
        val = input("  > ").strip()
        if not val:
            print("  请输入坐标，格式: x,y（例如: 1675,432）")
            continue
        try:
            parts = val.replace(" ", "").split(",")
            x = int(parts[0])
            y = int(parts[1])
            print(f"  输入坐标: ({x}, {y})")
            return x, y
        except (ValueError, IndexError):
            print("  格式错误，请重新输入，格式: x,y（例如: 1675,432）")


def manual_input_rect():
    print("\n  请手动输入矩形坐标，格式: left,top,right,bottom")
    print("  （左上角和右下角的坐标）")
    while True:
        val = input("  > ").strip()
        if not val:
            print("  请输入坐标，格式: left,top,right,bottom")
            continue
        try:
            parts = val.replace(" ", "").split(",")
            x1 = int(parts[0])
            y1 = int(parts[1])
            x2 = int(parts[2])
            y2 = int(parts[3])
            left = min(x1, x2)
            top = min(y1, y2)
            right = max(x1, x2)
            bottom = max(y1, y2)
            print(f"  输入坐标: ({left}, {top}, {right}, {bottom})")
            print(f"  宽度: {right - left}px, 高度: {bottom - top}px")
            return left, top, right, bottom
        except (ValueError, IndexError):
            print("  格式错误，请重新输入，格式: left,top,right,bottom")


def choose_calibrate_method():
    print("\n  选择校准方式:")
    print("    1 - 鼠标定位（将鼠标移到目标位置，3秒后自动记录）")
    print("    2 - 手动输入（直接输入坐标数字）")
    while True:
        ans = input("  请选择 [1/2，默认1]: ").strip()
        if ans == "" or ans == "1":
            return "mouse"
        elif ans == "2":
            return "manual"
        else:
            print("  请输入 1 或 2")


def calibrate_point(item, current_value):
    preview_path = None
    try:
        print(f"\n{'='*60}")
        print(f"  坐标校准 - {item['name']}")
        print(f"  当前坐标: ({current_value[0]}, {current_value[1]})")
        print(f"  描述: {item['desc']}")
        print(f"{'='*60}")

        print(f"\n  [预览] 正在截取当前坐标周围区域...")
        preview_path = capture_preview_point(
            current_value[0], current_value[1], item["key"]
        )
        if preview_path:
            print(f"  [预览] 预览图已生成，正在打开...")
            open_preview_image(preview_path)

        while True:
            ans = input(
                "\n  当前坐标是否正确？(y=正确, n=重新校准, s=跳过) [默认y]: "
            ).strip().lower()
            if ans == "" or ans == "y":
                return current_value
            elif ans == "s":
                return None
            elif ans == "n":
                method = choose_calibrate_method()
                if method == "mouse":
                    x, y = wait_and_capture(
                        "请将鼠标移动到按钮/点的位置，3秒后自动记录"
                    )
                else:
                    x, y = manual_input_point()

                print(f"\n  [预览] 正在截取新坐标周围区域...")
                new_preview = capture_preview_point(x, y, item["key"] + "_new")
                if new_preview:
                    print(f"  [预览] 新预览图已生成，正在打开...")
                    open_preview_image(new_preview)

                print(f"\n  记录结果: ({x}, {y})")
                confirm = input(
                    "  确认此坐标？(y=确认, r=重新校准) [默认y]: "
                ).strip().lower()
                if confirm == "" or confirm == "y":
                    delete_preview(new_preview)
                    return [x, y]
                else:
                    delete_preview(new_preview)
                    continue
    finally:
        delete_preview(preview_path)


def calibrate_rect(item, current_value):
    preview_path = None
    try:
        print(f"\n{'='*60}")
        print(f"  坐标校准 - {item['name']}")
        print(
            f"  当前坐标: ({current_value[0]}, {current_value[1]}, "
            f"{current_value[2]}, {current_value[3]})"
        )
        print(f"  描述: {item['desc']}")
        print(f"{'='*60}")

        print(f"\n  [预览] 正在截取当前区域...")
        preview_path = capture_preview_rect(current_value, item["key"])
        if preview_path:
            print(f"  [预览] 预览图已生成，正在打开...")
            open_preview_image(preview_path)

        print(f"\n  [OCR] 正在识别当前区域文字...")
        ocr_text = ocr_region_by_coord(*current_value)
        if ocr_text:
            print(f"  [OCR] 识别结果:")
            for line in ocr_text.split("\n")[:5]:
                print(f"    {line}")
            if len(ocr_text.split("\n")) > 5:
                print(f"    ...（共{len(ocr_text.split(chr(10)))}行）")
        else:
            print(f"  [OCR] 未识别到文字")

        while True:
            ans = input(
                "\n  当前坐标是否正确？(y=正确, n=重新校准, s=跳过) [默认y]: "
            ).strip().lower()
            if ans == "" or ans == "y":
                return current_value
            elif ans == "s":
                return None
            elif ans == "n":
                method = choose_calibrate_method()
                if method == "mouse":
                    print("\n  第一步：记录【左上角】")
                    x1, y1 = wait_and_capture(
                        "请将鼠标移动到区域的左上角，3秒后自动记录"
                    )
                    print("\n  第二步：记录【右下角】")
                    x2, y2 = wait_and_capture(
                        "请将鼠标移动到区域的右下角，3秒后自动记录"
                    )
                else:
                    x1, y1, x2, y2 = manual_input_rect()

                left = min(x1, x2)
                top = min(y1, y2)
                right = max(x1, x2)
                bottom = max(y1, y2)

                print(f"\n  [预览] 正在截取新区域...")
                new_preview = capture_preview_rect(
                    [left, top, right, bottom], item["key"] + "_new"
                )
                if new_preview:
                    print(f"  [预览] 新预览图已生成，正在打开...")
                    open_preview_image(new_preview)

                print(f"\n  [OCR] 正在识别新区域文字...")
                new_ocr = ocr_region_by_coord(left, top, right, bottom)
                if new_ocr:
                    print(f"  [OCR] 识别结果:")
                    for line in new_ocr.split("\n")[:5]:
                        print(f"    {line}")
                    if len(new_ocr.split("\n")) > 5:
                        print(f"    ...（共{len(new_ocr.split(chr(10)))}行）")
                else:
                    print(f"  [OCR] 未识别到文字")

                print(f"\n  记录结果: ({left}, {top}, {right}, {bottom})")
                print(f"  宽度: {right - left}px, 高度: {bottom - top}px")

                confirm = input(
                    "  确认此区域坐标？(y=确认, r=重新校准) [默认y]: "
                ).strip().lower()
                if confirm == "" or confirm == "y":
                    delete_preview(new_preview)
                    return [left, top, right, bottom]
                else:
                    delete_preview(new_preview)
                    continue
    finally:
        delete_preview(preview_path)


def build_config_from_profile(profile_data):
    regions = profile_data.get("regions", {})
    config = {"learn": {}, "test": {}}

    for item in COORD_ITEMS:
        key = item["key"]
        val = regions.get(key)
        if val is None:
            val = item["default"]

        path = item["path"]
        if path[0] == "learn":
            if len(path) == 2:
                config["learn"][path[1]] = val
            elif len(path) == 3:
                if path[1] not in config["learn"]:
                    config["learn"][path[1]] = [None, None, None, None]
                config["learn"][path[1]][path[2]] = val
        elif path[0] == "test":
            if len(path) == 2:
                config["test"][path[1]] = val
            elif len(path) == 3:
                if path[1] not in config["test"]:
                    config["test"][path[1]] = [None, None, None, None]
                config["test"][path[1]][path[2]] = val

    return config


def run_calibration_wizard(default_values=None):
    if default_values is None:
        default_values = {}

    print("\n" + "=" * 60)
    print("  🎯 坐标校准向导")
    print("=" * 60)
    print(f"\n  共 {len(COORD_ITEMS)} 个坐标项需要校准")
    print("  每一步会：")
    print("    1. 自动截取当前坐标区域的预览图并打开")
    print("    2. 对于OCR区域，实时显示识别结果")
    print("    3. 你可以选择 y=正确 / n=重新校准 / s=跳过")
    print("    4. 重新校准时可选择鼠标定位或手动输入")
    print("\n" + "=" * 60)

    input("\n  按 Enter 开始校准...")

    results = {}

    for idx, item in enumerate(COORD_ITEMS, 1):
        print(f"\n  [{idx}/{len(COORD_ITEMS)}] ", end="")

        current = default_values.get(item["key"], item["default"])

        if item["type"] == "point":
            result = calibrate_point(item, current)
        else:
            result = calibrate_rect(item, current)

        if result is not None:
            results[item["key"]] = result
        else:
            results[item["key"]] = current

    print("\n" + "=" * 60)
    print("  ✅ 坐标校准完成！")
    print("=" * 60)

    while True:
        profile_name = input("\n  请为此方案命名: ").strip()
        if profile_name:
            break
        print("  方案名称不能为空！")

    print(f"\n  确认保存方案 '{profile_name}' 吗？(y/n) [默认y]")
    ans = input("  > ").strip().lower()
    if ans == "" or ans == "y":
        if save_profile(profile_name, results):
            set_current_profile(profile_name)
            print(f"\n  ✅ 方案 '{profile_name}' 已保存！")
        else:
            print(f"\n  ❌ 方案保存失败")
    else:
        print("\n  已取消保存")
        return None

    return results, profile_name


def check_and_calibrate(monitor_input_func=None):
    current_profile_name = get_current_profile()
    profiles = list_profiles()

    print("\n" + "=" * 60)
    print("  📐 坐标方案检测")
    print("=" * 60)

    if current_profile_name:
        profile_data = load_profile(current_profile_name)
        if profile_data:
            print(f"\n  当前方案: {current_profile_name}")
            print(f"  更新时间: {profile_data.get('updated_at', '未知')}")
            print(f"  已配置坐标: {len(profile_data.get('regions', {}))}/{len(COORD_ITEMS)} 项")

            if monitor_input_func:
                ans = monitor_input_func("这是您的坐标方案吗？(y/n，默认y)", default="y")
            else:
                ans = input("\n  这是您的坐标方案吗？(y/n) [默认y]: ").strip().lower()

            if ans == "" or ans == "y":
                print(f"\n  ✅ 使用方案: {current_profile_name}")
                return build_config_from_profile(profile_data)

    if profiles and not current_profile_name:
        print("\n  已有方案:")
        for i, p in enumerate(profiles, 1):
            print(f"    {i}. {p['name']}")

        if monitor_input_func:
            choice = monitor_input_func("选择方案编号，或输入 n 新建方案", default="n")
        else:
            choice = input("\n  选择方案编号，或输入 n 新建方案: ").strip()

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(profiles):
                profile_data = load_profile(profiles[idx]["name"])
                if profile_data:
                    set_current_profile(profiles[idx]["name"])
                    print(f"\n  ✅ 使用方案: {profiles[idx]['name']}")
                    return build_config_from_profile(profile_data)

    print("\n  进入坐标校准向导...")
    time.sleep(1)

    result = run_calibration_wizard()
    if result:
        coord_data, profile_name = result
        profile_data = load_profile(profile_name)
        if profile_data:
            return build_config_from_profile(profile_data)

    return None


if __name__ == "__main__":
    print("坐标方案管理模块 - 测试模式")
    result = check_and_calibrate()
    if result:
        print("\n生成的 regions 配置:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
