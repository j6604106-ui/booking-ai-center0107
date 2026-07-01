import subprocess
import datetime
from config import settings


def init_kb_git():
    subprocess.run(["git", "init"], cwd=settings.kb_dir, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=settings.kb_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial KB commit"],
        cwd=settings.kb_dir,
        capture_output=True,
    )


def commit_kb_changes(agent_name: str):
    try:
        subprocess.run(
            ["git", "add", "."],
            cwd=settings.kb_dir,
            check=True,
            capture_output=True,
        )
        msg = (
            f"Auto-update: {agent_name} KB updated at "
            f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=settings.kb_dir,
            check=True,
            capture_output=True,
        )
    except Exception as e:
        print(f"Git commit failed: {e}")