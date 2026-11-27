@echo off
rem SF6 merge / differential insert (Issue #44)
rem Usage: tools\migration\merge.bat backups\sf6-backup-YYYYMMDD-HHMMSS.zip [--dry-run] ...
cd /d "%~dp0..\.."
python tools\migration\merge.py %*
