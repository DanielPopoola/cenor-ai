# Cerno AI Backend

This project is the backend for an AI-driven platform designed to help developers practice technical interviews. It lets you manage your candidate profile, store job descriptions, and engage in mock interview sessions with an AI that adapts to your performance and provides structured observations.

## Description

Preparing for technical interviews can be tough, but this backend aims to make it easier. It powers a platform where users can upload their CV and connect their GitHub profile, which the system then processes and structures using AI. You can also save job postings you're interested in. The core feature is the mock interview experience: you'll engage in a multi-segment interview session with an AI that acts as your interviewer, adjusting its questions based on your responses. After a session, the system provides detailed observations about your performance across key behavioral categories, helping you understand your strengths and areas for improvement.

## Features

*   **User Authentication**: Secure Google OAuth integration for user login, leveraging stateless, HMAC-signed session cookies.
*   **Dynamic Configuration**: Centralized, type-safe settings management via Pydantic, with environment-variable overrides and production safety checks.
*   **Database Management**: Uses SQLAlchemy for ORM, Alembic for database migrations, and supports SQLite (in-memory for tests, file-based for dev/prod).
*   **Candidate Profile**: Allows users to upload CVs (PDF/DOCX) for AI-driven text extraction and structuring, and connect GitHub profiles for comprehensive analysis, including top languages and account age computation.
*   **Job Posting Management**: Enables users to save and retrieve job postings, including raw descriptions, for targeted interview practice.
*   **AI-Powered Interview Sessions**: Orchestrates multi-segment mock interview sessions, with an AI acting as the interviewer, adapting questions based on candidate responses and predefined strictness modes.
*   **Segmented Interviews**: Breaks down interviews into specialized segments (e.g., programming algorithms, system design), each with its own checklist and duration.
*   **Code Editor Support**: Integrates optional code snapshot submission for specific interview segments (e.g., coding challenges), allowing the AI to observe code alongside conversational responses.
*   **Performance Observation**: After a session, a background AI task (`Observer`) analyzes the full transcript to extract detailed observations on key behaviors, like ambiguity clarification, intentional approach choices, and communication effectiveness.
*   **Robust API Design**: Implements a consistent `APIResponse` envelope, structured JSON logging with request IDs, in-memory IP rate limiting, and comprehensive exception handling (domain-specific errors, request validation).
*   **Security Measures**: Includes prompt injection sanitization for AI inputs and CSRF protection for OAuth flows.
*   **Resilience**: Incorporates a `@retry_transient` decorator for handling temporary external API failures gracefully.

## Installation

To get this project up and running locally, follow these steps:

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/DanielPopoola/cenor-ai.git
    cd cenor-ai
    ```

2.  **Set up Environment**:
    *   Make sure you have Python 3.13 installed.
    *   Create a virtual environment:
        ```bash
        python -m venv .venv
        source .venv/bin/activate # On Windows: .venv\Scripts\activate
        ```
    *   Install project dependencies:
        ```bash
        pip install -r requirements.txt
        ```
        (If you don't have a `requirements.txt` file, you can generate one from `pyproject.toml` or install directly via `pip install ".[dev]"` for all dependencies).

3.  **Configure Environment Variables**:
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Open `.env` and fill in the required values. At a minimum, you'll need:
        *   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: Obtained from the Google Cloud Console for OAuth.
        *   `GOOGLE_REDIRECT_URI`: Set to `http://localhost:8000/api/v1/auth/google/callback` for local development.
        *   `COOKIE_SIGNING_SECRET`: A long, random string. **Never use the default `dev-only-insecure-secret-change-me` in production environments.**
        *   `LLM_API_KEY`: Your API key for an OpenAI-compatible LLM provider (e.g., OpenAI, Anthropic). The application can boot without it, but AI-driven features will be unavailable.
        *   `GITHUB_API_TOKEN`: (Optional) A GitHub Personal Access Token if you want to enable GitHub profile syncing.
        *   `DATABASE_URL`: Defaults to `sqlite:///./cerno.db` if unset, creating a local SQLite database file.

## Usage

Once configured, you can run the application and interact with its API.

1.  **Apply Database Migrations**:
    This step sets up your database schema.
    ```bash
    alembic upgrade head
    ```
    If this is your very first time setting up with a persistent database, you might need to generate an initial migration first. You can do this by running `alembic revision --autogenerate -m "create initial tables"` after ensuring your SQLAlchemy models are discoverable by Alembic (check `migrations/env.py`).

2.  **Start the Development Server**:
    ```bash
    uvicorn app.main:app --reload
    ```
    The application will be accessible at `http://localhost:8000`.

3.  **Access API Documentation**:
    You can explore the interactive API documentation at `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (Redoc).

### Key API Endpoints

Here are some of the main endpoints you can interact with:

*   **Authentication (`/api/v1/auth`)**:
    *   `GET /google`: Initiates the Google OAuth login flow.
    *   `GET /google/callback`: Handles the Google OAuth callback.
    *   `POST /logout`: Logs the current user out.
    *   `GET /me`: Retrieves information about the current authenticated user.

*   **Candidate Profile (`/api/v1/profile`)**:
    *   `GET /`: Fetches the current user's candidate profile.
    *   `POST /cv`: Uploads a CV file (PDF or DOCX) for AI processing.
    *   `POST /github`: Connects a GitHub profile using a username for AI structuring.

*   **Job Postings (`/api/v1/jobs`)**:
    *   `POST /`: Creates a new job posting.
    *   `GET /`: Lists all job postings for the current user.
    *   `GET /{job_posting_id}`: Retrieves a specific job posting.

*   **Interview Sessions (`/api/v1/sessions`)**:
    *   `POST /`: Creates a new AI-powered interview session.
    *   `GET /`: Lists all interview sessions for the current user.
    *   `GET /{session_id}`: Retrieves a specific session's details.
    *   `POST /{session_id}/turns`: Submits a candidate's response (turn) during an active session.
    *   `POST /{session_id}/next-question`: Requests the next question from the AI interviewer, especially after a segment transition.
    *   `POST /{session_id}/end`: Manually ends an active session.

*   **Session Observations (`/api/v1/sessions/{session_id}/observations`)**:
    *   `GET /api/v1/sessions/{session_id}/observations`: Retrieves the AI-generated observations for a completed session.

## Technologies Used

| Technology | Description | Link |
| :--------- | :---------- | :--- |
| **Python** | Primary programming language | [python.org](https://www.python.org/) |
| **FastAPI** | High-performance web framework for building APIs | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| **SQLAlchemy** | SQL Toolkit and Object Relational Mapper | [sqlalchemy.org](https://www.sqlalchemy.org/) |
| **Alembic** | Database migration tool for SQLAlchemy | [alembic.sqlalchemy.org](https://alembic.sqlalchemy.org/) |
| **Pydantic** | Data validation and settings management | [pydantic.dev](https://pydantic.dev/) |
| **Pytest** | Robust testing framework | [docs.pytest.org](https://docs.pytest.org/) |
| **httpx** | A fully featured HTTP client for Python | [www.python-httpx.org](https://www.python-httpx.org/) |
| **pypdf** | PDF library for Python | [pypdf.readthedocs.io](https://pypdf.readthedocs.io/en/stable/) |
| **python-docx** | Read, write, and create Word .docx files | [python-docx.readthedocs.io](https://python-docx.readthedocs.io/en/latest/) |
| **OpenAI** | Integrates with OpenAI-compatible LLM APIs | [openai.com](https://openai.com/) |
| **Ruff** | Extremely fast Python linter and formatter | [docs.astral.sh/ruff/](https://docs.astral.sh/ruff/) |
| **ty** | Type checking CLI tool | [docs.astral.sh/ty/](https://docs.astral.sh/ty/) |

## License

This project is currently under development and does not yet have a formal license defined.

## Author Info

Connect with me!

*   LinkedIn: [Your LinkedIn](https://linkedin.com/in/yourusername)
*   X (Twitter): [@yourhandle](https://x.com/yourhandle)

---
[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-blue?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Pytest](https://img.shields.io/badge/Pytest-green?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/Ruff-orange?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)

[![Readme was generated by Dokugen](https://img.shields.io/badge/Readme%20was%20generated%20by-Dokugen-brightgreen)](https://www.npmjs.com/package/dokugen)