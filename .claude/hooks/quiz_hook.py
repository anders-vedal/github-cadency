#!/usr/bin/env python3
"""
PreToolUse hook that blocks git commit until the user passes a quiz.

Receives JSON on stdin: {session_id, cwd, hook_event_name, tool_name, tool_input}
Exit 0 = allow, Exit 2 = block (stderr shown to Claude)
"""
import json
import sys
import subprocess
import hashlib
import os

BYPASS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "quiz-tokens")


def get_staged_diff(cwd):
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True, cwd=cwd,
    )
    return result.stdout


def get_staged_diff_stat(cwd):
    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True, text=True, cwd=cwd,
    )
    return result.stdout


def diff_hash(diff_content):
    return hashlib.sha256(diff_content.encode()).hexdigest()[:16]


def truncate(text, max_lines=200):
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines truncated)"


def main():
    data = json.load(sys.stdin)

    # Toggle: create .claude/hooks/quiz_disabled to skip the quiz
    hook_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(hook_dir, "quiz_disabled")):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        sys.exit(0)

    cwd = data.get("cwd", ".")
    diff_content = get_staged_diff(cwd)

    if not diff_content.strip():
        sys.exit(0)  # Nothing staged, let git handle the error

    h = diff_hash(diff_content)
    token_path = os.path.join(BYPASS_DIR, f"quiz-bypass-{h}")

    if os.path.exists(token_path):
        os.remove(token_path)
        sys.exit(0)

    stat = get_staged_diff_stat(cwd)
    diff_truncated = truncate(diff_content)

    sys.stderr.write(f"""QUIZ REQUIRED — commit blocked until the user demonstrates understanding of the changes.

Instructions for Claude:
1. Read the staged diff below carefully.
2. Ask the user 2-3 specific, detailed questions about the implementation — for example:
   - What does a particular function/component do and why was it implemented this way?
   - What would happen in a specific edge case?
   - Why was a particular design decision made?
3. Do NOT accept vague or surface-level answers. The user should demonstrate genuine understanding.
4. If the user answers correctly, run this command to create a bypass token:
   python .claude/hooks/quiz_bypass.py create
5. Then retry the original commit command.
6. If the user answers incorrectly, explain what was wrong and ask again. Do NOT create the bypass token until answers are satisfactory.

=== FILES CHANGED ===
{stat}
=== DIFF ===
{diff_truncated}
""")
    sys.exit(2)


if __name__ == "__main__":
    main()
