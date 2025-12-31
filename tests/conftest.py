"""Shared test utilities and fixtures for TaskNet tests"""

import subprocess
import sys
from pathlib import Path


# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Path to verifier script
VERIFIER_SCRIPT = 'src/smt/tasknet_verifier.py'

# Test data directories
VALID_TASKNET_DIR = 'tests/tasknet_files/valid'
INVALID_TASKNET_DIR = 'tests/tasknet_files/invalid'


def verify(tasknet_file, valid=True, check=True, mode='plan'):
    """
    Run the TaskNet verifier on a given file.

    Args:
        tasknet_file: Name of the .tn file (e.g., 'tasknet1.tn')
        valid: If True, looks in valid/ directory, otherwise invalid/
        check: If True, raises AssertionError if verifier exits with non-zero code
        mode: 'plan' for optimization mode or 'verify' for satisfiability mode

    Returns:
        str: The stdout output from the verifier

    Raises:
        AssertionError: If check=True and verifier exits with non-zero returncode
    """
    directory = VALID_TASKNET_DIR if valid else INVALID_TASKNET_DIR
    tasknet_path = f"{directory}/{tasknet_file}"

    cmd = [sys.executable, VERIFIER_SCRIPT, tasknet_path, '--mode', mode]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT
    )

    if check and result.returncode != 0:
        raise AssertionError(f"Verifier failed with returncode {result.returncode}:\n{result.stderr}")

    return result.stdout


def contains_all(output, expected_strings):
    """
    Assert that output contains all expected strings.

    Args:
        output: The string to search in
        expected_strings: List of strings that should all be present

    Raises:
        AssertionError: If any expected string is not found
    """
    for expected in expected_strings:
        assert expected in output, f"Expected string not found: {expected}"


def verify_out(tasknet_file, mode='plan'):
    """
    Curried function: verify a tasknet file and check expected output strings.

    Args:
        tasknet_file: Name of the .tn file (e.g., 'tasknet1.tn')
        mode: 'plan' for optimization mode or 'verify' for satisfiability mode

    Returns:
        Function that takes expected_strings as *args and asserts they're all in output
    """
    def check_output(*expected_strings):
        output = verify(tasknet_file, mode=mode)
        if not expected_strings:
            print(output)
        contains_all(output, expected_strings)
    return check_output
