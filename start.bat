@echo off
title 刷单词脚本
echo 正在启动刷单词脚本...
echo 脚本运行中，按 Ctrl+C 停止
echo 日志文件: f:\desktop\项目\BrushEnglish\logs\
echo.

start /min "" "f:\desktop\项目\BrushEnglish\venv\Scripts\pythonw.exe" "f:\desktop\项目\BrushEnglish\完整脚本_学习测试循环.py"

echo 脚本已启动（后台运行）
echo 若要停止，请打开任务管理器结束 pythonw.exe 进程
echo.
pause