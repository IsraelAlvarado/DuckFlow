"""
core/kaggle_client.py — Kaggle CLI wrapper used by the kaggle router.
"""
from __future__ import annotations

import os
import subprocess


def kaggle_env() -> dict:
    env = os.environ.copy()
    key = os.getenv("api_token_kaggle", "")
    user = os.getenv("KAGGLE_USERNAME", "")
    if user:
        env["KAGGLE_USERNAME"] = user
    if key and key != "your_kaggle_api_token_here":
        env["KAGGLE_KEY"] = key
    return env


def run_cmd(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=kaggle_env(),
        timeout=timeout,
    )