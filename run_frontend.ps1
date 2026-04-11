# run_frontend.ps1
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m streamlit run streamlit_app/app.py --server.port 8501