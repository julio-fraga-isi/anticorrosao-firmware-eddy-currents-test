@echo off
setlocal enabledelayedexpansion
title ISI Sensoriamento - Eddy Current Test Bench Launcher

echo =======================================================================
echo          ISI Sensoriamento - Eddy Current Test Bench Launcher
echo =======================================================================
echo.

:: 1. Verificar se o Python está instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado no sistema!
    echo Por favor, instale o Python 3 (3.8 a 3.12 recomendado) e adicione-o ao PATH do Windows.
    echo Baixe em: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: 2. Verificar/criar pastas necessarias
echo [INFO] Verificando estrutura de pastas...
set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR%.."
set "DATASET_DIR=%APP_DIR%\datasets"

if not exist "%DATASET_DIR%" (
    echo [INFO] Criando pasta de datasets em: %DATASET_DIR%
    mkdir "%DATASET_DIR%"
)

:: 3. Instalar dependencias necessarias via pip
echo [INFO] Verificando e instalando bibliotecas necessarias (PyQt5, pyqtgraph, pyserial, numpy)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install PyQt5 pyqtgraph pyserial numpy --quiet
if %errorlevel% neq 0 (
    echo [AVISO] Houve um problema ao instalar as bibliotecas via pip global. 
    echo Tentando instalar com permissao de usuario (--user)...
    python -m pip install PyQt5 pyqtgraph pyserial numpy --user --quiet
)

:: 4. Executar o script principal
echo.
echo [INFO] Iniciando a Interface Grafica (GUI)...
echo.
cd /d "%APP_DIR%"
python eddy_current_plotter_gui.py

if %errorlevel% neq 0 (
    echo.
    echo [ERRO] A interface encerrou com codigo de erro %errorlevel%.
    pause
)
