@echo off
chcp 65001 >nul
title ???? Agent

cd /d "%~dp0"

echo.
echo ====================================
echo   ???? Agent
echo ====================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python ?????? PATH ?
    pause
    exit /b 1
)

REM Check .env
if not exist .env (
    echo [WARN] .env ??????? .env.example ??...
    copy .env.example .env
    echo [INFO] ??? .env ???? DeepSeek API Key
)

REM Install deps if needed
echo [INFO] ????...
python -c "import aiohttp,langchain_openai,pydantic_settings" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] ??????...
    pip install aiohttp langchain langchain-openai langchain-core pydantic pydantic-settings httpx python-dotenv tenacity
)

echo.
echo [INFO] ????...
echo [INFO] ???????: http://localhost:8000
echo [INFO] ? Ctrl+C ??
echo.

python -m app.main

pause
