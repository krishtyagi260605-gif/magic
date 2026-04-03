import os
import subprocess
import tempfile
from typing import Any
from app.config import get_settings

def execute_python_sandbox(code: str, timeout: int = 15) -> dict[str, Any]:
    """
    Executes Python code safely. Tries Docker first, falls back to subprocess.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        f_path = f.name
    
    has_docker = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    image = get_settings().sandbox_docker_image
    
    try:
        if has_docker:
            cmd = [
                "docker", "run", "--rm", "--network", "none", "-m", "256m",
                "-v", f"{f_path}:/app/script.py:ro",
                image, "python", "/app/script.py"
            ]
            used_docker = True
        else:
            cmd = ["python3", f_path]
            used_docker = False
            
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (completed.stdout + "\n" + completed.stderr).strip() or "Execution completed successfully."
        return {
            "ok": completed.returncode == 0,
            "output": out,
            "commands_run": [f"docker run {image}..." if used_docker else "python3 script.py"]
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Execution timed out after {timeout} seconds."}
    except Exception as exc:
        return {"ok": False, "output": f"Sandbox execution failed: {exc}"}
    finally:
        os.unlink(f_path)