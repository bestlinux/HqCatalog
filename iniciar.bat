@echo off
title Catalogador de HQs - Streamlit
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Servidor do Catalogador de HQs...
echo ========================================================
echo.
echo No seu smartphone conectado na mesma rede Wi-Fi, acesse:
echo http://192.168.15.3:8501
echo.
echo No computador, acesse:
echo http://localhost:8501
echo ========================================================
echo.
py -3 -m streamlit run app.py
pause
