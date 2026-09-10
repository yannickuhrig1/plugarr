@echo off
setlocal
cd /d "%~dp0"
title PlugArr - Demo carte V2
set "PYTHONPATH=%~dp0src"
echo PlugArr - nouvelle carte des connexions V2
echo Sources : "%~dp0src"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto python_missing
if not exist ".venv-local-demo\Scripts\python.exe" py -3 -m venv .venv-local-demo
if errorlevel 1 goto failure
".venv-local-demo\Scripts\python.exe" -c "import textual; from plugarr import dashboard, connections, orchestrator" >nul 2>&1
if errorlevel 1 (
  ".venv-local-demo\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto failure
)
set PLUGARR_NO_SELF_UPDATE=1
".venv-local-demo\Scripts\python.exe" scripts\preview_console.py --open
if errorlevel 1 goto failure
exit /b 0
:python_missing
echo Python 3.11 ou plus recent est requis, avec la commande py.
echo Une fois Python installe, relancez ce fichier.
pause
exit /b 1
:failure
echo Le lancement a echoue. Copiez le message affiche ci-dessus.
pause
exit /b 1
