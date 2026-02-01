@echo off
REM Скрипт для подготовки и публикации на GitHub (Windows)

echo.
echo 🚀 TopNews Bot - Push to GitHub Script
echo ======================================
echo.

REM Проверяем что репозиторий инициализирован
if not exist ".git" (
    echo ❌ Git репозиторий не инициализирован
    echo.
    echo Инициализируем репозиторий в GitHub Desktop или:
    echo.
    echo git init
    echo git remote add origin https://github.com/jfsagro-glitch/topnews.git
    echo git branch -M main
    echo.
    echo Затем запустите этот скрипт снова
    pause
    exit /b 1
)

echo 📋 Проверяем статус репозитория:
git status
echo.

echo 🔍 Проверяем готовность к Railway:
python check_railway_ready.py

if errorlevel 1 (
    echo.
    echo ❌ Проект не готов к Railway deployment
    echo Пожалуйста, исправьте ошибки выше
    pause
    exit /b 1
)

echo.
echo ✅ Проект готов!
echo.

echo 📦 Добавляем все файлы в Git:
git add .

echo.
set /p commit_message="💬 Введите сообщение коммита (Enter для 'Update TopNews Bot'): "
if "%commit_message%"=="" set commit_message=Update TopNews Bot

echo.
echo 📝 Создаем коммит:
git commit -m "%commit_message%"

echo.
echo 🚀 Пушим в GitHub:
git push -u origin main

if errorlevel 0 (
    echo.
    echo ✅ Успешно запушено в GitHub!
    echo.
    echo 🚀 Следующие шаги для Railway:
    echo 1. Перейдите на https://railway.app
    echo 2. Создайте новый проект (New Project)
    echo 3. Выберите 'Deploy from GitHub'
    echo 4. Выберите jfsagro-glitch/topnews
    echo 5. Установите переменные окружения:
    echo    - TELEGRAM_TOKEN
    echo    - TELEGRAM_CHANNEL_ID
    echo 6. Нажмите Deploy
    echo.
    echo Railway автоматически подхватит Procfile и запустит бота
) else (
    echo.
    echo ❌ Ошибка при пуше
)

pause
