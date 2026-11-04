@echo off
"%~dp0artifacts\vpnn-control.exe" -listen 127.0.0.1:8098 -state "%~dp0private\control\state.json" -admin-secret-file "%~dp0private\control\admin.secret"
pause
