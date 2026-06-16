@echo off
cd /d "C:\ProgramData\SOFIA"
call venv\Scripts\activate
start /B python main.py
