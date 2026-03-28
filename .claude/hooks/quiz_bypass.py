#!/usr/bin/env python3
"""
Quiz bypass token management.

Usage:
    python quiz_bypass.py create   — create a bypass token for current staged diff
    python quiz_bypass.py clean    — remove expired tokens
"""
import sys
import subprocess
import hashlib
import os
import time

BYPASS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "quiz-tokens")
TOKEN_MAX_AGE = 300  # 5 minutes


def get_staged_diff_hash():
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True,
    )
    return hashlib.sha256(result.stdout.encode()).hexdigest()[:16]


def clean_tokens():
    if not os.path.exists(BYPASS_DIR):
        return
    now = time.time()
    for name in os.listdir(BYPASS_DIR):
        path = os.path.join(BYPASS_DIR, name)
        try:
            with open(path) as f:
                created = float(f.read().strip())
            if now - created > TOKEN_MAX_AGE:
                os.remove(path)
        except (ValueError, OSError):
            os.remove(path)


def create_token():
    os.makedirs(BYPASS_DIR, exist_ok=True)
    clean_tokens()
    h = get_staged_diff_hash()
    token_path = os.path.join(BYPASS_DIR, f"quiz-bypass-{h}")
    with open(token_path, "w") as f:
        f.write(str(time.time()))
    print(f"Quiz bypass token created (diff hash: {h})")


def main():
    if len(sys.argv) < 2:
        print("Usage: quiz_bypass.py [create|clean]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "create":
        create_token()
    elif cmd == "clean":
        clean_tokens()
        print("Stale tokens cleaned.")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
