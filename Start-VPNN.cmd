@echo off
setlocal
set "VPNN_EXE=%~dp0client\build\windows\x64\runner\Debug\VPNN.exe"
if not exist "%VPNN_EXE%" (
  echo Windows build is missing. Run tools\build-windows.ps1 first.
  pause
  exit /b 1
)
start "VPNN foundation - safe mode" /D "%~dp0client\build\windows\x64\runner\Debug" "%VPNN_EXE%"
