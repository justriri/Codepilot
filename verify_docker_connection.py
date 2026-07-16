"""
Docker connectivity verification.

Standalone and deliberately independent of the rest of this project (no
SandboxManager, no agent config, no imports from agent/ or providers/)
— this verifies ONE thing only: can docker.from_env() reach your local
Docker Engine at all. Nothing else in this repo is touched or modified
by running this.

Steps:
  1. Connect via docker.from_env() (the exact call SandboxManager makes).
  2. Print the Docker Engine version.
  3. List existing containers (proves the API, not just the socket, works).
  4. Create a temporary container (alpine:latest).
  5. Confirm it actually started.
  6. Remove it.
  7. Print a clear PASS or FAIL.

Usage:
    python verify_docker_connection.py
"""

import sys

RESULT = {"pass": True}  # flips to False on any failure; used for the final line


def fail(message: str, fix: str = None):
    RESULT["pass"] = False
    print(f"\nFAILED: {message}")
    if fix:
        print(f"\nHow to fix:\n{fix}")


def main():
    print("=== Step 1: Connect via docker.from_env() ===")
    try:
        import docker
    except ImportError:
        fail(
            "the 'docker' Python package isn't installed.",
            "pip install -r requirements.txt  (or: pip install docker)",
        )
        print_result()
        sys.exit(1)

    try:
        client = docker.from_env()
    except Exception as e:
        fail(
            f"could not connect: {e}",
            "This almost always means Docker Desktop isn't running (docker.from_env()\n"
            "negotiates the API version immediately, so a construction failure and a\n"
            "'daemon unreachable' failure look identical here).\n"
            "  1. Open Docker Desktop and wait for it to report 'Docker Desktop is running'.\n"
            "  2. Confirm from a terminal: docker info\n"
            "     (if that ALSO fails, it's Docker Desktop itself, not this script or the SDK)\n"
            "  3. Re-run this script.",
        )
        print_result()
        sys.exit(1)
    print("Connected.")

    print("\n=== Step 2: Print Docker Engine version ===")
    try:
        version_info = client.version()
        print(f"Engine version: {version_info.get('Version')}")
        print(f"API version:    {version_info.get('ApiVersion')}")
        print(f"OS/Arch:        {version_info.get('Os')}/{version_info.get('Arch')}")
    except Exception as e:
        fail(f"connected, but client.version() failed: {e}", "Check Docker Desktop's own status/logs.")
        print_result()
        sys.exit(1)

    print("\n=== Step 3: List existing containers ===")
    try:
        existing = client.containers.list(all=True)
        if existing:
            for c in existing:
                print(f"  {c.short_id}  {c.name}  ({c.status})")
        else:
            print("  (none — that's fine, just confirms the API call itself works)")
    except Exception as e:
        fail(f"could not list containers: {e}")
        print_result()
        sys.exit(1)

    print("\n=== Step 4: Create a temporary container (alpine:latest) ===")
    container = None
    try:
        container = client.containers.run("alpine:latest", command="sleep 30", detach=True)
        print(f"Created: {container.short_id}")
    except Exception as e:
        fail(
            f"could not create the container: {e}",
            "If the error mentions pulling the image, check your network/firewall/VPN\n"
            "isn't blocking Docker Hub, and that you have disk space free.",
        )
        print_result()
        sys.exit(1)

    print("\n=== Step 5: Confirm it actually started ===")
    try:
        container.reload()
        status = container.status
        print(f"Status: {status}")
        if status != "running":
            fail(f"container status is '{status}', expected 'running'.")
        else:
            # Extra confirmation beyond just the status field: run something inside it.
            exit_code, output = container.exec_run("echo container-is-alive")
            output_text = output.decode().strip()
            print(f"exec_run confirmation: exit_code={exit_code}, output='{output_text}'")
            if exit_code != 0 or output_text != "container-is-alive":
                fail("container is 'running' but exec_run didn't behave as expected.")
            else:
                print("Confirmed: container is running and responds to commands.")
    except Exception as e:
        fail(f"could not confirm container state: {e}")

    print("\n=== Step 6: Remove the container ===")
    try:
        container.remove(force=True)
        print(f"Removed {container.short_id}.")
    except Exception as e:
        fail(
            f"cleanup failed: {e}",
            f"Remove it manually: docker rm -f {container.short_id if container else '<container_id>'}",
        )

    print_result()
    sys.exit(0 if RESULT["pass"] else 1)


def print_result():
    print("\n" + "=" * 40)
    print("RESULT: PASS" if RESULT["pass"] else "RESULT: FAIL")
    print("=" * 40)
    if RESULT["pass"]:
        print("Docker Desktop is correctly configured. SandboxManager will work.")


if __name__ == "__main__":
    main()
