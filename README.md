# Prioriti
Student Schedule App

Backend Startup Commands: 
Set-Location 'FILEPATH' -ErrorAction Stop
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Confirm Database Connection with the following command (confirm that it returns HTTP 200): 
curl.exe -i http://127.0.0.1:8000/health

Architecture:
- The backend uses a temporary, shared local-development owner.
- The application runs locally on IP 127.0.0.1.
- Currently supported API routes are /health, POST/GET /tasks, and POST/GET /commitments.
- Inputs require timezone-aware timestamps. Stored and returned timestamps use UTC.
- Include the backend startup command using a relative backend folder path.
