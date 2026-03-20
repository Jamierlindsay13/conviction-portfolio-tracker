@echo off
set PATH=C:\Users\jamie\AppData\Local\Programs\Python\Python312;C:\Users\jamie\AppData\Local\Programs\Python\Python312\Scripts;%PATH%
cd /d C:\Users\jamie\conviction-portfolio-tracker
streamlit run app.py --server.port 8507 --server.headless false
pause
