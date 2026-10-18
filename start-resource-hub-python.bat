@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "APP=%~dp0resource_hub.pyw"
set "APP_ARGS=%*"
set "LOG=%~dp0resource_hub_launcher.log"
set "LAUNCH_EXE="
set "LAUNCHW_EXE="

> "%LOG%" echo Launcher started at %date% %time%

if not defined LAUNCH_EXE (
  if exist "D:\miniconda3\python.exe" (
    >> "%LOG%" echo Testing: D:\miniconda3\python.exe
    "D:\miniconda3\python.exe" -c "import tkinterdnd2, pystray" >nul 2>nul
    if errorlevel 1 (
      >> "%LOG%" echo Failed dependency check: D:\miniconda3\python.exe
    ) else (
      set "LAUNCH_EXE=D:\miniconda3\python.exe"
      if exist "D:\miniconda3\pythonw.exe" set "LAUNCHW_EXE=D:\miniconda3\pythonw.exe"
    )
  ) else (
    >> "%LOG%" echo Missing: D:\miniconda3\python.exe
  )
)

if not defined LAUNCH_EXE (
  if exist "C:\Python314\python.exe" (
    >> "%LOG%" echo Testing: C:\Python314\python.exe
    "C:\Python314\python.exe" -c "import tkinterdnd2, pystray" >nul 2>nul
    if errorlevel 1 (
      >> "%LOG%" echo Failed dependency check: C:\Python314\python.exe
    ) else (
      set "LAUNCH_EXE=C:\Python314\python.exe"
      if exist "C:\Python314\pythonw.exe" set "LAUNCHW_EXE=C:\Python314\pythonw.exe"
    )
  ) else (
    >> "%LOG%" echo Missing: C:\Python314\python.exe
  )
)

if not defined LAUNCH_EXE (
  if exist "E:\python.exe" (
    >> "%LOG%" echo Testing: E:\python.exe
    "E:\python.exe" -c "import tkinterdnd2, pystray" >nul 2>nul
    if errorlevel 1 (
      >> "%LOG%" echo Failed dependency check: E:\python.exe
    ) else (
      set "LAUNCH_EXE=E:\python.exe"
      if exist "E:\pythonw.exe" set "LAUNCHW_EXE=E:\pythonw.exe"
    )
  ) else (
    >> "%LOG%" echo Missing: E:\python.exe
  )
)

if not defined LAUNCH_EXE (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined LAUNCH_EXE (
      set "CANDIDATE=%%~fI"
      set "CANDIDATEW=%%~dpIpythonw.exe"
      >> "%LOG%" echo Testing: !CANDIDATE!
      "!CANDIDATE!" -c "import tkinterdnd2, pystray" >nul 2>nul
      if errorlevel 1 (
        >> "%LOG%" echo Failed dependency check: !CANDIDATE!
      ) else (
        set "LAUNCH_EXE=!CANDIDATE!"
        if exist "!CANDIDATEW!" set "LAUNCHW_EXE=!CANDIDATEW!"
      )
    )
  )
)

if defined LAUNCHW_EXE (
  >> "%LOG%" echo Launching with: !LAUNCHW_EXE!
  start "" "!LAUNCHW_EXE!" "%APP%" %APP_ARGS%
  goto :eof
)

if defined LAUNCH_EXE (
  >> "%LOG%" echo Launching with: !LAUNCH_EXE!
  start "" "!LAUNCH_EXE!" "%APP%" %APP_ARGS%
  goto :eof
)

>> "%LOG%" echo No Python environment with tkinterdnd2 and pystray was found.
echo Resource Hub could not find a Python environment with tkinterdnd2 and pystray installed.
echo.
echo Log file: %LOG%
pause
