"""
Regression test for safe import of main.py without Redis.

This test ensures that the application can be imported even when Redis
is unavailable, preventing the TypeError that previously occurred due to
catching redis.exceptions.* classes at import time.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def test_main_imports_without_redis():
    """
    Verify that main.py can be imported in a clean Python subprocess
    without a running Redis instance.
    """
    # Walk up from the test file until we find main.py
    test_file = Path(__file__).resolve()
    project_root = test_file.parent
    while project_root != project_root.parent:
        if (project_root / "main.py").exists():
            break
        project_root = project_root.parent
    else:
        pytest.fail("Could not locate project root containing main.py")

    main_py = project_root / "main.py"

    # Run a separate Python process that only does "import main"
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        pytest.fail(
            f"Importing main.py failed with return code {result.returncode}.\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )

    # If we reach here, the import succeeded without raising TypeError
    assert "TypeError" not in result.stderr
    assert "BaseException" not in result.stderr
