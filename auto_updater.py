#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动更新模块
===========
功能：
1. 读取本地版本号 (app_version.json)
2. 访问服务器获取最新版本
3. 比较版本号，判断是否需要更新
4. 用户确认后下载新包
5. 生成更新脚本 updater.ps1，退出主程序让更新脚本完成覆盖+重启
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import zipfile
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


def get_base_dir():
    """获取程序根目录（exe模式/脚本模式通用）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()

# 找配置：优先 _internal\app_version.json（打包模式），其次根目录
INTERNAL_DIR = BASE_DIR / "_internal"
if INTERNAL_DIR.exists():
    APP_VERSION_FILE = INTERNAL_DIR / "app_version.json"
    if not APP_VERSION_FILE.exists():
        APP_VERSION_FILE = BASE_DIR / "app_version.json"
else:
    APP_VERSION_FILE = BASE_DIR / "app_version.json"


def load_app_version():
    """读取本地版本配置"""
    default_cfg = {
        "version": "1.0.0",
        "update_url": "https://example.com/update/latest_version.json",  # 改成你自己的更新地址
        "check_interval_hours": 6,
        "last_check": ""
    }
    if APP_VERSION_FILE.exists():
        try:
            with open(APP_VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            merged = {**default_cfg, **data}
            return merged
        except Exception as e:
            print(f"[更新] 读取版本文件失败: {e}，使用默认配置")
    return default_cfg


def save_last_check(app_cfg):
    """保存最后检查时间"""
    try:
        app_cfg["last_check"] = datetime.now().isoformat()
        if APP_VERSION_FILE.exists():
            with open(APP_VERSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["last_check"] = app_cfg["last_check"]
            with open(APP_VERSION_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def compare_versions(v1, v2):
    """
    语义化版本比较
    return: -1 (v1<v2), 0 (equal), 1 (v1>v2)
    """
    try:
        parts1 = [int(x) for x in re.findall(r'\d+', v1)]
        parts2 = [int(x) for x in re.findall(r'\d+', v2)]
        max_len = max(len(parts1), len(parts2))
        parts1 += [0] * (max_len - len(parts1))
        parts2 += [0] * (max_len - len(parts2))
        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            elif a > b:
                return 1
        return 0
    except Exception:
        return 0


def fetch_latest_version(update_url, timeout=10):
    """访问服务器获取最新版本信息"""
    try:
        req = urllib.request.Request(update_url, headers={
            'User-Agent': 'BrushEnglishUpdater/1.0',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='ignore')
            return json.loads(raw)
    except urllib.error.URLError as e:
        raise Exception(f"无法连接更新服务器 (URLError: {e.reason})")
    except Exception as e:
        raise Exception(f"获取更新信息失败: {e}")


def download_file(url, dst_path, progress_cb=None, timeout=30):
    """
    下载文件，支持进度回调
    progress_cb(received_bytes, total_bytes)
    """
    def report_hook(block_num, block_size, total_size):
        received = min(block_num * block_size, total_size)
        if progress_cb:
            progress_cb(received, total_size)

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'BrushEnglishUpdater/1.0'
        })
        urllib.request.urlretrieve(url, str(dst_path), reporthook=report_hook)
        return True
    except Exception as e:
        if dst_path.exists():
            try:
                dst_path.unlink()
            except Exception:
                pass
        raise Exception(f"下载失败: {e}")


def build_updater_script(zip_path, app_dir, app_exe_name, backup_dir_name):
    r"""
    生成更新脚本 updater.ps1（主程序退出后运行）
    逻辑：
      1. 等主程序退出（轮询进程）
      2. 备份旧文件到 app_dir\_backup_版本号_时间戳
      3. 解压 zip 到 app_dir（覆盖）
      4. 重启新的主程序
      5. 删除 updater.ps1 和 zip
    """
    updater_path = app_dir / "updater.ps1"
    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    ps1 = f"""
# ============================================================
# 刷单词助手 - 自动更新脚本（由主程序自动生成）
# 运行时间: {datetime.now()}
# ============================================================

$ErrorActionPreference = "Continue"

$appDir = "{app_dir}"
$zipPath = "{zip_path}"
$appExe = Join-Path $appDir "{app_exe_name}"
$backupDir = Join-Path $appDir "_backup_{ts}"
$procName = "{app_exe_name.replace('.exe','')}"

Write-Host ""
Write-Host "========================================="
Write-Host "   刷单词助手 - 正在更新..."
Write-Host "========================================="
Write-Host ""

# --- 1. 等主程序退出 ---
Write-Host "[1/5] 等待主程序退出..." -ForegroundColor Cyan
$maxWait = 60
for ($i = 0; $i -lt $maxWait; $i++) {{
    $proc = Get-Process -Name $procName -ErrorAction SilentlyContinue
    if (-not $proc) {{ break }}
    Start-Sleep -Seconds 1
    Write-Host "  等待 $($i+1)/${{maxWait}}s..." -ForegroundColor DarkGray
}}
Write-Host "  ✓ 主程序已退出" -ForegroundColor Green

# --- 2. 备份旧文件 ---
Write-Host "[2/5] 备份旧版本到: $backupDir" -ForegroundColor Cyan
try {{
    if (Test-Path $backupDir) {{ Remove-Item $backupDir -Recurse -Force }}
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $skipDirs = @("_backup_", "Umi-OCR", "logs", "学习截图", "测试截图")
    Get-ChildItem $appDir -File | Where-Object {{
        $_.Name -ne $(Split-Path $zipPath -Leaf) -and $_.Name -ne "updater.ps1"
    }} | ForEach-Object {{
        Copy-Item $_.FullName (Join-Path $backupDir $_.Name) -Force
    }}
    Get-ChildItem $appDir -Directory | Where-Object {{
        $skipDirs -notcontains $_.Name -and -not $_.Name.StartsWith("_backup_")
    }} | ForEach-Object {{
        Copy-Item $_.FullName (Join-Path $backupDir $_.Name) -Recurse -Force
    }}
    Write-Host "  ✓ 备份完成" -ForegroundColor Green
}} catch {{
    Write-Host "  ⚠ 备份失败（继续更新）: $_" -ForegroundColor Yellow
}}

# --- 3. 解压覆盖 ---
Write-Host "[3/5] 解压更新包..." -ForegroundColor Cyan
try {{
    if (-not (Get-Command Expand-Archive -ErrorAction SilentlyContinue)) {{
        Write-Host "  系统缺少 Expand-Archive，改用第三方解压..." -ForegroundColor Yellow
        throw "No Expand-Archive"
    }}
    Expand-Archive -Path $zipPath -DestinationPath $appDir -Force
    Write-Host "  ✓ 解压完成" -ForegroundColor Green
}} catch {{
    Write-Host "  ✗ 解压失败: $_" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车键退出，更新未完成"
    exit 1
}}

# --- 4. 清理临时文件 ---
Write-Host "[4/5] 清理临时文件..." -ForegroundColor Cyan
try {{
    if (Test-Path $zipPath) {{ Remove-Item $zipPath -Force }}
    Write-Host "  ✓ 清理完成" -ForegroundColor Green
}} catch {{
    Write-Host "  ⚠ 清理失败: $_" -ForegroundColor Yellow
}}

# --- 5. 启动新程序 ---
Write-Host "[5/5] 启动新版本..." -ForegroundColor Cyan
try {{
    Start-Process $appExe
    Write-Host "  ✓ 新版本已启动！" -ForegroundColor Green
}} catch {{
    Write-Host "  ✗ 启动失败，请手动双击: $appExe" -ForegroundColor Red
}}

# 自删除
Write-Host ""
Write-Host "========================================="
Write-Host "  更新完成！3秒后自动关闭此窗口"
Write-Host "========================================="
Write-Host ""
Start-Sleep -Seconds 3
try {{ Remove-Item $MyInvocation.MyCommand.Path -Force }} catch {{}}
"""

    # 写文件（UTF8 无 BOM）
    utf8NoBom = type('UTF8NoBom', (object,), {})()
    import codecs
    with codecs.open(str(updater_path), 'w', 'utf-8-sig') as f:
        # utf-8-sig 写 PowerShell 最兼容
        f.write(ps1)

    return updater_path


def run_updater(updater_path):
    """启动更新脚本并退出主程序"""
    try:
        # 用 PowerShell 执行 updater.ps1，绕过 ExecutionPolicy
        ps_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        if not Path(ps_exe).exists():
            ps_exe = "powershell.exe"

        args = [
            ps_exe,
            "-ExecutionPolicy", "Bypass",
            "-NoProfile",
            "-File", str(updater_path)
        ]
        subprocess.Popen(args, close_fds=True)
        return True
    except Exception as e:
        print(f"[更新] 启动更新脚本失败: {e}")
        return False


def format_size(bytes_size):
    """人类可读的文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


import re  # 挪到底部，避免版本比较找不到 re


# ============================================================
# 对外主入口：main() 最开头调用此函数
# ============================================================
def check_and_ask_update(force_check=False):
    """
    检查更新，用户确认后执行下载+更新
    return:
      "skip"      - 无需更新 / 用户跳过
      "updating"  - 已启动更新脚本，调用方应立即退出
      "error"     - 检查失败（不影响正常使用）
    """
    app_cfg = load_app_version()
    current_ver = app_cfg["version"]
    update_url = app_cfg["update_url"]
    interval_hours = app_cfg.get("check_interval_hours", 6)

    print()
    print("=" * 60)
    print(f"  🎯 版本检查  当前版本: v{current_ver}")
    print("=" * 60)

    # --- 频率控制（非强制检查时） ---
    if not force_check and app_cfg.get("last_check"):
        try:
            last = datetime.fromisoformat(app_cfg["last_check"])
            if datetime.now() - last < timedelta(hours=interval_hours):
                print(f"  · 距上次检查不足 {interval_hours} 小时，跳过本次检测")
                print(f"    (下次自动检查: {(last + timedelta(hours=interval_hours)).strftime('%Y-%m-%d %H:%M')})")
                print()
                return "skip"
        except Exception:
            pass

    # --- 访问服务器 ---
    print(f"  检查地址: {update_url}")
    print("  正在获取最新版本...")
    try:
        latest = fetch_latest_version(update_url)
    except Exception as e:
        print(f"  ✗ 检查失败：{e}")
        print("  中文说明：服务器没响应或网络不通，继续使用当前版本")
        print()
        return "error"

    save_last_check(app_cfg)
    latest_ver = latest.get("latest_version", "0.0.0")
    release_notes = latest.get("release_notes", "")
    download_url = latest.get("download_url", "")
    file_size = latest.get("file_size", 0)
    force = latest.get("force_update", False)
    release_date = latest.get("release_date", "")

    print(f"  服务器最新版: v{latest_ver}  ({release_date})")

    # --- 版本比较 ---
    cmp = compare_versions(current_ver, latest_ver)
    if cmp >= 0:
        print("  ✓ 已是最新版本")
        print()
        return "skip"

    # --- 有新版本，询问用户 ---
    print()
    print("  🎉 发现新版本！")
    print(f"    新版本: v{current_ver} → v{latest_ver}")
    if release_date:
        print(f"    发布日期: {release_date}")
    if file_size:
        print(f"    更新包大小: {format_size(file_size)}")
    if release_notes:
        print(f"    更新内容:")
        for line in release_notes.splitlines():
            print(f"      {line}")
    if force:
        print("    ⚠ 此版本为强制更新")
    print()

    # 交互询问
    while True:
        if force:
            prompt_str = "  此版本必须更新，按 [Enter] 立即开始更新: "
        else:
            prompt_str = "  是否立即更新？[y=更新, n=稍后再说] (默认 y): "
        try:
            choice = input(prompt_str).strip().lower()
        except Exception:
            choice = "y" if force else "n"

        if choice == "" or choice == "y":
            break
        elif choice == "n" and not force:
            print("  已跳过，下次启动时再提示")
            print()
            return "skip"
        else:
            if force:
                continue
            print("  请输入 y 或 n")

    # --- 开始下载 ---
    if not download_url:
        print("  ✗ 服务器未提供下载地址")
        print()
        return "error"

    print()
    print(f"  下载地址: {download_url}")
    print("  开始下载（请耐心等待，600MB 左右可能需要几分钟）...")

    tmp_zip = BASE_DIR / f"_update_v{latest_ver}.zip"
    last_percent = -1

    def on_progress(received, total):
        nonlocal last_percent
        if total <= 0:
            return
        percent = int(received * 100 / total)
        if percent != last_percent and percent % 5 == 0:
            print(f"    下载进度: {percent}%  ({format_size(received)} / {format_size(total)})")
            last_percent = percent

    try:
        download_file(download_url, tmp_zip, progress_cb=on_progress, timeout=3600)
    except Exception as e:
        print(f"  ✗ 下载失败：{e}")
        print("  中文说明：网络中断或服务器无响应，请稍后重试")
        if tmp_zip.exists():
            try:
                tmp_zip.unlink()
            except Exception:
                pass
        print()
        return "error"

    print(f"  ✓ 下载完成: {tmp_zip.name}")
    print()

    # --- 生成更新脚本并执行 ---
    print("  准备启动更新程序（主程序将退出，更新完成后自动重启）...")
    app_exe_name = Path(sys.executable).name if getattr(sys, 'frozen', False) else "刷单词助手.exe"

    try:
        updater_path = build_updater_script(tmp_zip, BASE_DIR, app_exe_name, "_backup")
    except Exception as e:
        print(f"  ✗ 生成更新脚本失败: {e}")
        print()
        return "error"

    print(f"  更新脚本: {updater_path}")
    time.sleep(1.5)

    if run_updater(updater_path):
        print("  ✓ 更新程序已启动，主程序即将退出")
        print("  请耐心等待更新完成（会有一个黑色更新窗口）")
        print()
        time.sleep(2)
        return "updating"
    else:
        print("  ✗ 启动更新程序失败，您可以手动解压更新包覆盖")
        print(f"    更新包路径: {tmp_zip}")
        print()
        return "error"


if __name__ == "__main__":
    # 单独运行：强制检查更新（调试用）
    result = check_and_ask_update(force_check=True)
    print(f"结果: {result}")