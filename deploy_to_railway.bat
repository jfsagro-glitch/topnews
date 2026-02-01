@echo off
REM Quick Railway Deployment Guide (Windows batch version)
REM Быстрое руководство развертывания на Railway

chcp 65001 > nul
cls

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║           TopNews Bot - Railway Deployment Quick Guide            ║
echo ║                    Быстрое развертывание за 5 минут              ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM Шаг 1
echo 📋 Шаг 1: Получите TELEGRAM_TOKEN
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 1. Откройте Telegram
echo 2. Найдите @BotFather
echo 3. Отправьте /newbot
echo 4. Следуйте инструкциям
echo 5. Скопируйте токен (выглядит как 123456:ABC-DEF1234...)
echo.
echo Пример: 123456789:ABCdefGhijKlmnoPqrsTuvWxyz-1234567890
echo.
set /p TELEGRAM_TOKEN=8559718970:AAEHOd2UOKlVqwuMfd7oGJp756tfR3Ng9OY

echo.
echo ✅ Токен сохранен
echo.

REM Шаг 2
echo 📋 Шаг 2: Получите TELEGRAM_CHANNEL_ID
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 1. Создайте новый ПРИВАТНЫЙ канал в Telegram
echo 2. Добавьте вашего бота администратором
echo 3. Добавьте @userinfobot в канал
echo 4. Напишите @userinfobot /info
echo 5. Скопируйте Chat ID (отрицательное число, например -1001234567890)
echo.
set /p TELEGRAM_CHANNEL_ID=-1003717409166

echo.
echo ✅ Channel ID сохранен
echo.

REM Шаг 3
echo 📋 Шаг 3: Проверка готовности
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
python final_deployment_check.py

if errorlevel 1 (
    echo.
    echo ❌ Проверка не пройдена
    pause
    exit /b 1
)

echo.
echo ✅ Все проверки пройдены!
echo.

REM Шаг 4
echo 📋 Шаг 4: Публикация в GitHub
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

git add .
set /p commit_msg=Enter
if "%commit_msg%"=="" set commit_msg=Prepare for Railway deployment

git commit -m "%commit_msg%"
git push origin main

if errorlevel 1 (
    echo.
    echo ❌ Ошибка при пуше
    pause
    exit /b 1
)

echo.
echo ✅ Код успешно запушен в GitHub
echo.

REM Шаг 5
echo 📋 Шаг 5: Развертывание на Railway
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 🚀 Следуйте инструкциям:
echo.
echo 1. Откройте https://railway.app
echo 2. Нажмите 'New Project'
echo 3. Выберите 'Deploy from GitHub'
echo 4. Авторизуйтесь GitHub
echo 5. Выберите jfsagro-glitch/topnews
echo 6. Нажмите 'Deploy'
echo.
echo 7. После создания проекта перейдите в 'Variables'
echo.
echo 8. Установите переменные:
echo    TELEGRAM_TOKEN=%TELEGRAM_TOKEN%
echo    TELEGRAM_CHANNEL_ID=%TELEGRAM_CHANNEL_ID%
echo.
echo    (также опционально):
echo    CHECK_INTERVAL_SECONDS=120
echo    LOG_LEVEL=INFO
echo.
echo 9. Нажмите 'Deploy'
echo.
echo ⏳ Railway начнет деплой (1-2 минуты)
echo.
echo ✅ Готово! Бот запустится автоматически
echo.

echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                    🎉 РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО!                   ║
echo ║                                                                    ║
echo ║ Ваш TopNews Bot сейчас в облаке на Railway                       ║
echo ║                                                                    ║
echo ║ Проверьте:                                                         ║
echo ║ 1. Railway Dashboard - Logs (должно быть "Bot started")           ║
echo ║ 2. Telegram бот - /help (должны видеть команды)                  ║
echo ║ 3. Ваш канал (новости должны появляться каждые 2 минуты)         ║
echo ║                                                                    ║
echo ║ Документация: https://github.com/jfsagro-glitch/topnews          ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

pause
