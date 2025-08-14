@echo off
echo JSON to Tabular Converter - Setup and Run
echo ==========================================

echo Installing required packages...
pip install -r requirements.txt

echo.
echo Starting the server...
echo Open your browser and go to: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python run_server.py

pause