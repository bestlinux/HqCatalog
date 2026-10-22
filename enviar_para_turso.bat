@echo off
title HqCatalog - Enviar SQLite Local para Turso Cloud
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Envio: SQLite Local -^> Turso Cloud...
echo ========================================================
echo.
py -3.14 sincronizar_banco.py --upload
echo.
pause
