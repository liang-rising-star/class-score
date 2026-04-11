@echo off
chcp 65001 >nul
echo.
echo 正在执行恢复出厂设置...
echo.
python "%~dp0reset.py"
echo.
pause
