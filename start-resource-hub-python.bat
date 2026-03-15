@echo off
setlocal
set "APP=%~dp0resource_hub.pyw"

where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%APP%"
) else (
  where pythonw >nul 2>nul
  if %errorlevel%==0 (
    start "" pythonw "%APP%"
  ) else (
    python "%APP%"
  )
)
