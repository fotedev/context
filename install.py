"""Install dependencies for the Context tool."""
import subprocess
import sys


def install(package: str) -> None:
    """Install a package using pip."""
    _ = subprocess.check_call([sys.executable, "-m", "pip", "install", package])


packages = ["tiktoken", "textual"]

for pkg in packages:
    print(f"Installing {pkg}...")
    try:
        install(pkg)
        print(f"  ✓ {pkg} installed")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ {pkg} failed: {e}")

print("\nDone. Core CLI has no dependencies — tiktoken and textual are optional.")
