@echo off
set OUTPUT=project_dump.txt

echo ===== PROJECT DUMP ===== > %OUTPUT%
echo Generated: %date% %time% >> %OUTPUT%
echo. >> %OUTPUT%

REM Przeszukaj wszystkie pliki .py .json .txt
for /r %%f in (*.py *.json *.txt) do (

    REM pomijamy niechciane foldery
    echo %%f | findstr /i "\.git __pycache__ venv .venv build dist" >nul
    if errorlevel 1 (

        echo ================================================== >> %OUTPUT%
        echo FILE: %%f >> %OUTPUT%
        echo ================================================== >> %OUTPUT%
        echo. >> %OUTPUT%

        REM numeracja linii
        setlocal enabledelayedexpansion
        set /a line=1
        for /f "usebackq delims=" %%l in ("%%f") do (
            echo !line!: %%l >> %OUTPUT%
            set /a line+=1
        )
        endlocal

        echo. >> %OUTPUT%
        echo. >> %OUTPUT%
    )
)

echo.
echo Dump zapisany do %OUTPUT%
pause
