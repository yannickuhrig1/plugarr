@echo off
setlocal
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\src"
set "PLUGARR_NO_SELF_UPDATE=1"
set "PLUGARR_PYTHON=py -3"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  set "PLUGARR_PYTHON=python"
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if errorlevel 1 goto python_missing
)
if not exist ".venv-web-local\Scripts\python.exe" (
  echo Preparation de l'environnement Python local...
  %PLUGARR_PYTHON% -m venv .venv-web-local
  if errorlevel 1 goto failure
)
".venv-web-local\Scripts\python.exe" -c "from plugarr import webwizard; from zoneinfo import ZoneInfo; ZoneInfo('Europe/Paris')" >nul 2>&1
if errorlevel 1 (
  echo Installation des dependances. Internet est necessaire cette premiere fois.
  ".venv-web-local\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto failure
)
if "%~1"=="demo" (
  echo DEMONSTRATION : aucune installation Docker ne sera effectuee.
  ".venv-web-local\Scripts\python.exe" -m plugarr --lang fr web --demo
) else if "%~1"=="tui" (
  ".venv-web-local\Scripts\python.exe" -m plugarr --lang fr --interface tui
) else (
  echo Mode reel : l'assistant demandera confirmation avant toute installation.
  ".venv-web-local\Scripts\python.exe" -m plugarr --lang fr
)
if errorlevel 1 goto failure
exit /b 0
:python_missing
echo Python 3.11 ou plus recent est requis. Installez-le puis relancez ce fichier.
pause
exit /b 1
:failure
echo Le lancement a echoue. Conservez le message affiche ci-dessus.
pause
exit /b 1
