import asyncio
import sys

from app.graph import run_magic
from app.config import get_settings

def main():
    print(get_settings().llm_provider)
    plan, outputs, final, task_trace = run_magic(
        "create a simple file named test.txt",
        execute=False,
    )
    print("FINAL:", final)
    print("OUTPUTS:", outputs)
    print("TRACE:", task_trace)

if __name__ == "__main__":
    main()
