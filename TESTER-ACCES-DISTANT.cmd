@echo off
setlocal
title PlugArr - Test acces distant et mobile
if not exist "%~dp0previews\acces-distant.html" (
  echo La page de demonstration est introuvable.
  pause
  exit /b 1
)
start "" "%~dp0previews\acces-distant.html"
