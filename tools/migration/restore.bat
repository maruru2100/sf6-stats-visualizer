@echo off
rem SF6 restore (Issue #32)
rem Usage: tools\migration\restore.bat backups\sf6-migration-YYYYMMDD-HHMMSS.zip --force [--dry-run] ...
cd /d "%~dp0..\.."
python tools\migration\restore.py %*
