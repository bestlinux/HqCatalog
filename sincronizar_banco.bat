@echo off
title HqCatalog - Sincronizar Turso Cloud para SQLite Local
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Sincronizacao Turso Cloud -> SQLite Local...
echo ========================================================
echo.
py -3.14 sincronizar_banco.py
echo.
pause
