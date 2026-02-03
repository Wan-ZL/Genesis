"""Status API endpoint."""
import re
from typing import Optional
from fastapi import APIRouter
from pathlib import Path

router = APIRouter()


def extract_section(content: str, section_name: str) -> Optional[str]:
    """Extract a section from markdown content."""
    lines = content.split("\n")
    in_section = False
    section_lines = []
    for line in lines:
        if line.startswith(f"## {section_name}"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.strip():
                section_lines.append(line.strip())
    return " ".join(section_lines) if section_lines else None


def extract_result_from_runlog(content: str) -> Optional[str]:
    """Extract result from runlog content."""
    # Look for [RUN_STATUS] section or ## Result
    match = re.search(r'result\s*=\s*(\w+)', content)
    if match:
        return match.group(1)
    # Try ## Result section
    result = extract_section(content, "Result")
    if result:
        # Extract first word (SUCCESS, PARTIAL, BLOCKED)
        first_word = result.split()[0] if result else None
        if first_word in ["SUCCESS", "PARTIAL", "BLOCKED"]:
            return first_word
    return None


@router.get("/health")
async def health_check():
    """Simple health check endpoint for service monitoring."""
    return {"status": "healthy"}


@router.get("/status")
async def get_status():
    """Get system status including Claude Code state."""
    agent_dir = Path(__file__).parent.parent.parent.parent / "agent"

    # Read agent/state.md for current focus
    state_path = agent_dir / "state.md"
    claude_code_focus = None
    if state_path.exists():
        content = state_path.read_text()
        claude_code_focus = extract_section(content, "Current Focus")

    # Find and parse latest runlog
    runlog_dir = agent_dir / "runlog"
    last_run = None
    if runlog_dir.exists():
        runlogs = sorted(runlog_dir.glob("*.md"), reverse=True)
        if runlogs:
            latest_file = runlogs[0]
            result = None
            try:
                content = latest_file.read_text()
                result = extract_result_from_runlog(content)
            except Exception:
                pass
            last_run = {
                "file": latest_file.name,
                "result": result
            }

    return {
        "status": "running",
        "version": "0.1.0",
        "claude_code_focus": claude_code_focus,
        "last_run": last_run
    }
