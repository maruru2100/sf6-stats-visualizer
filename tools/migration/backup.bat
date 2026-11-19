@echo off
rem SF6 backup / migration export (Issue #32)
rem Usage: tools\migration\backup.bat [--mode migration|backup] [--no-secrets] [--dry-run] ...
cd /d "%~dp0..\.."
python tools\migration\backup.py %*
