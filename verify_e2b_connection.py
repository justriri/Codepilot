"""
E2B sandbox connectivity verification.

Run this BEFORE the full pipeline test. It checks ONE thing only:
can the E2B SDK create and destroy a cloud sandbox using your API key?

Usage:
    python verify_e2b_connection.py

Requires:
    E2B_API_KEY set in .env (or environment)
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def fail(message: str, hint: str = "") -> None:
    print(f"FAILED: {message}")
    if hint:
        print(f"Hint: {hint}")
    sys.exit(1)


def main() -> None:
    print("=== Step 1: Check E2B_API_KEY ===")
    api_key = os.environ.get("E2B_API_KEY", "").strip()
    if not api_key:
        fail(
            "E2B_API_KEY is not set.",
            "Add E2B_API_KEY=... to your .env file. Get a key at https://e2b.dev/docs",
        )
    print("E2B_API_KEY is set.")

    print("\n=== Step 2: Import E2B SDK ===")
    try:
        from e2b import Sandbox
    except ImportError:
        fail(
            "the 'e2b' package is not installed.",
            "pip install -r requirements.txt  (or: pip install e2b)",
        )
    print("E2B SDK imported successfully.")

    print("\n=== Step 3: Create a temporary cloud sandbox ===")
    sandbox = None
    try:
        sandbox = Sandbox.create()
        print(f"Created sandbox: {sandbox.sandbox_id}")
    except Exception as e:
        fail(
            f"E2B sandbox creation failed: {e}",
            "Confirm your API key is valid and your E2B account has sandbox quota.",
        )

    print("\n=== Step 4: Run a command inside the sandbox ===")
    try:
        result = sandbox.commands.run("echo sandbox-is-alive")
        output = (result.stdout or "").strip()
        if output != "sandbox-is-alive":
            fail(f"unexpected command output: {output!r}")
        print("Confirmed: sandbox responds to commands.")
    except Exception as e:
        fail(f"command execution failed: {e}")

    print("\n=== Step 5: Destroy the sandbox ===")
    try:
        sandbox.kill()
        print("Sandbox destroyed.")
    except Exception as e:
        fail(
            f"failed to destroy sandbox: {e}",
            f"Remove it manually from the E2B dashboard if needed (id: {sandbox.sandbox_id}).",
        )

    print("\n" + "=" * 60)
    print("E2B is correctly configured. SandboxManager will work.")
    print("=" * 60)


if __name__ == "__main__":
    main()
