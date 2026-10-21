# Prioriti
    Prioriti is a local Student Organizational Planner built with React, TypeScript, FastAPI, and MongoDB.
    Users enter tasks, fixed commitments, generate a 7-day schedule, and see explanations for tasks that are unable to be assigned.

# Existing Features
    - Create/List tasks with deadlines, priorities, categories, estimated minutes, and status
    - Create/List one-off commitments
    - Persistent tasks and commitments in MongoDB
    - Deadline-first greedy schedule generation
    - Display scheduled/unscheduled tasks and commitments in a chronological agenda with explanations for tasks that are unable to be schedule
    - Validate inputs and display connection/save errors

## Architecture
    The React frontend sends JSON requests to FastAPI. Fast API validates inputs, reads/writes MongoDB records, and runs the scheduler.
    MongoDB runs in Docker Desktop and the frontend/backend run locally on the development machine.

    ```
    frontend/
    src/
        App.tsx        Forms, saved lists, and schedule display
        api.ts         HTTP requests and API error handling
        types.ts       Shared frontend data types
        time.ts        New York time conversion and formatting

    backend/
    app/
        main.py        Application startup, cross-origin resource sharing, and error handling
        db.py          MongoDB connection and indexes
        models.py      Request & response validation
        routes.py      API endpoints
        scheduler.py   Greedy scheduling logic
    tests/
        test_scheduler.py
    ```

## Requirements
    The local development environment uses the following:
    - Windows PowerShell
    - Node.js 22.23.2 and npm
    - Python 3.14.6
    - Docker Desktop with its Linux Engine running
    - MongoDB 8.0 supplied by the Docker Container

## First-time Setup Instructions
    1. Clone the repository and enter the root directory:
    ``` POWERSHELL
        git clone https://github.com/mattdoescoding/Prioriti.git
        Set-Location .\Prioriti
    ```

    2a. Create the backend virtual environment using the installed Python interpreter. For standard Windows Python launcher installation:
    ``` POWERSHELL
        py -3.14 -m venv backend\.venv
    ```
    2b. For an Astral-managed Python installation, use this command instead:
    ``` POWERSHELL
        py -V:Astral/CPython3.14.6 -m venv backend\.venv
    ```

    3. Install frontend & backend dependencies:
    ``` POWERSHELL
        .\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
        npm.cmd --prefix frontend ci
    ```

    4. Create local environment files if they do not already exist:
    ``` POWERSHELL
        if (-not (Test-Path backend\.env)) {
            Copy-Item backend\.env.example backend\.env
        }

        if (-not (Test-Path frontend\.env)) {
            Copy-Item frontend\.env.example frontend\.env
        }
    ```
    Default settings and ports are the following:
        File        |       Variable        |           Default
    `backend/.env`  |   `MONGODB_URI`       |   `mongodb://127.0.0.1:27017`
    `backend/.env`  |   `MONGODB_DB`        |   `prioriti`
    `backend/.env`  |   `FRONTEND_ORIGIN`   |   `http://127.0.0.1:5173`
    `frontend/.env` |   `VITE_API_BASE_URL` |   `http://127.0.0.1:8000`

    Actual .env files are ignored by Git. Commit `.env.example` files with non-secret example values. Frontend `VITE_` variables are browser-visible and should not contain secrets.

    5. Open Docker Desktop and wait for its engine to start. Create the MongoDB container once:
    ``` POWERSHELL
        docker run -d --name prioriti-mongo -p 127.0.0.1:27017:27017 -v prioriti-mongo-data:/data/db mongo:8.0
    ```
    The named volume `prioriti-mongo-data` stores the database across container restarts.
    If the container already exists, then use the startup commands below.

## Run Locally
        Open each application terminal in the repository root

        1. Start MongoDB
            Open Docker Desktop and wait for its engine to run.
            ``` POWERSHELL
                docker start prioriti-mongo
            ```

            Wait a few seconds, then check database readiness:
            ``` POWERSHELL
                docker exec prioriti-mongo mongosh --quiet --eval 'db.adminCommand({ping:1})'
            ```

            Confirm that the ping returns `ok: 1`. If the connection is initially refused, wait for a few seconds and repeat the ping until `ok: 1` is returned.

        2. Start FastAPI
            In one PowerShell terminal:
            ```powershell
                Set-Location .\backend
                .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
            ```

            Leave this terminal running. Refer to the following pages:
            API documentation:      (http://127.0.0.1:8000/docs)
            Database health check:  (http://127.0.0.1:8000/health)

            A healthy response is:
            ``` JSON
                {"status":"ok","database":"connected"}
            ```
        3. Start React
            In a second PowerShell terminal, starting from the repository root:
            ``` POWERSHELL
                Set-Location .\frontend
                npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
            ```

            Open Prioriti:          (http://127.0.0.1:5173)
            Use this exact address so the browser origin matches the backend cross-origin resource sharing (CORS) configuration.
        
        4. Stop the Application
            Press Ctrl+C in each application terminal and allow shutdown to finish.
            Stop MongoDB with:
            ``` POWERSHELL
                docker stop prioriti-mongo
            ```
            Stopping the container preserves its database volume.

## Scheduling Behavior
    The scheduler considers seven consecutive days starting from the selected date.

    - Daily availability is 9AM to 9PM America/New_York, including weekends.
    - New work starts no earlier than the selected window or the current time, whichever is later.
    - Completed tasks are excluded fromn the scheduler.
    - Tasks are ordered by earliest deadline, then highest priority, then ID.
    - Priority 3 is high, 2 is medium, and 1 is low.
    - Estimated durations round up to the next 15-minute increment.
    - Each task occupies one continuous block within one day.
    - Tasks avoid commitments and previously placed tasks.
    - Scheduled tasks finish by their deadlines.
    - Tasks that cannot fit receive an explanation for why they were not scheduled.

    The scheduler greedily selects the earliest valid opening for each task. It does not reconsider earlier placements, so another arrangement may fit more tasks.
    Tasks and commitments are persisted. Generated schedules are calculated previews and must be regenerated after a page refresh or changes to saved inputs.

## API Endpoints
    METHOD      |       ENDPOINT                |              PURPOSE
    GET         |      `/health`                |       Check the API and database connection
    GET         |      `/tasks`                 |       List saved tasks
    POST        |      `/tasks`                 |       Create a task
    GET         |      `/commitments`           |       List saved commitments
    POST        |      `/commitments`           |       Create a commitment
    POST        |      `/schedule/generate`     |       Generate a seven-day schedule
    
    Schedule generation accepts a starting date:
    ``` JSON
        {"week_start":"2026-10-22"}
    ```
    Use an appropriate date when testing. The response includes scheduled tasks, unscheduled tasks/reasons, and overlapping commitments.

## Automated Checks
    Starting from the repository root:

    ``` POWERSHELL
        Set-Location .\backend
        .\.venv\Scripts\python.exe -m pytest -q

        Set-Location ..\frontend
        npm.cmd run build
        npm.cmd run lint

        Set-Location ..
    ```

    The scheduler tests cover overlap avoidance, deadlines, an overbooked week, completed tasks, duration rounding, planning start time, ordering, and daylight-saving boundaries.
    Scheduler unit tests use a fixed reference time and do not require MongoDB to run.

## Current Limitations
    This version uses a shared, backend-assigned `local-development`. Authentication and private user accounts are not yet implemented. Run the application locally on loopback addresses with previously listed commands.
    The current interface supports creating and listing records. Editing, deleting, and updating existing task status are not yet implemented.

    Pending implementations:
    - Authentication and ownership enforcement
    - Recurring commitments and availability configuration
    - Completion and duration logging
    - Travel buffers, pinned blocks, and scheduling optimization
    - Automated Canvas calendar imports and authorized course/assignment API integration (needs Rutgers confirmation)
    - Duration prediction and caching
    - Public deployment