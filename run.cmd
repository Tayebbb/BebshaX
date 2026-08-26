@echo off
if "%~1"=="" goto dev
if /I "%~1"=="backend" goto backend
if /I "%~1"=="frontend" goto frontend
if /I "%~1"=="dev" goto dev

:backend
node scripts\run_backend.js
goto end

:frontend
node scripts\dev.js
goto end

:dev
node scripts\dev.js
goto end

:end
