import os
from pathlib import Path
import jinja2

def generate_fastapi_backend(project_dir: Path, spec: dict) -> str:
    app_dir = project_dir / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    
    reqs = ["fastapi", "uvicorn", "pydantic"]
    db = spec.get("database", "")
    auth = spec.get("auth", "")
    if db == "postgresql":
        reqs.append("sqlalchemy")
        reqs.append("psycopg2-binary")
    elif db == "sqlite":
        reqs.append("sqlalchemy")
    if auth == "jwt":
        reqs.append("fastapi-jwt-auth")
        reqs.append("passlib[bcrypt]")
        
    (project_dir / "requirements.txt").write_text("\n".join(reqs), encoding="utf-8")
    (project_dir / ".env.example").write_text("DATABASE_URL=postgresql://user:pass@localhost/db\nSECRET_KEY=supersecret\n", encoding="utf-8")
    (project_dir / "Dockerfile").write_text("FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt\nCOPY . .\nCMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n", encoding="utf-8")
    
    main_template = """from fastapi import FastAPI, Depends
{% if spec.database == 'postgresql' or spec.database == 'sqlite' %}
from sqlalchemy import create_engine
{% endif %}
{% if spec.auth == 'jwt' %}
from fastapi_jwt_auth import AuthJWT
{% endif %}

app = FastAPI(title="{{ spec.project_name | default('Backend API') }}")

{% if spec.database %}
@app.on_event("startup")
async def startup():
    # connect to {{ spec.database }}
    pass
{% endif %}

@app.get('/')
def read_root():
    return {"message": "Welcome to the backend API"}
"""
    template = jinja2.Template(main_template)
    (app_dir / "main.py").write_text(template.render(spec=spec), encoding="utf-8")
    return "python3 -m uvicorn app.main:app --reload"