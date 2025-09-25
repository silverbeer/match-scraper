#!/usr/bin/env python3
"""
Test Guardian - Automated test review and creation tool
Usage: uv run python scripts/test-review.py [command]

Commands:
  review     - Review recent changes and suggest tests
  fix        - Fix failing tests
  coverage   - Analyze test coverage gaps
  create     - Create tests for specific file/function
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: str) -> tuple[int, str, str]:
    """Run a shell command and return exit code, stdout, stderr."""
    result = subprocess.run(
        cmd.split(), capture_output=True, text=True, cwd=Path.cwd()
    )
    return result.returncode, result.stdout, result.stderr


def get_recent_changes():
    """Get recent git changes for review."""
    _, stdout, _ = run_command("git log --oneline -10")
    print("📋 Recent commits:")
    print(stdout)

    _, diff_output, _ = run_command("git diff HEAD~3..HEAD --stat")
    print("\n📊 Changed files:")
    print(diff_output)


def check_test_status():
    """Check current test status."""
    print("🧪 Running test suite...")
    code, stdout, stderr = run_command("uv run python -m pytest tests/unit/ -v --tb=short")

    if code == 0:
        print("✅ All tests passing!")
    else:
        print("❌ Some tests failing:")
        print(stderr)

    return code == 0


def analyze_coverage():
    """Analyze test coverage."""
    print("📈 Analyzing test coverage...")
    run_command("uv run python -m pytest tests/unit/ --cov=src --cov-report=term-missing")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        command = "review"
    else:
        command = sys.argv[1]

    print(f"🚀 Test Guardian - {command.title()} Mode")
    print("=" * 50)

    if command == "review":
        get_recent_changes()
        print("\n" + "=" * 50)
        check_test_status()
        print("\n💡 Tip: Use '/agents test-guardian' in Claude Code for detailed analysis")

    elif command == "fix":
        if not check_test_status():
            print("\n🔧 Use '/agents test-guardian' to analyze and fix failing tests")

    elif command == "coverage":
        analyze_coverage()

    elif command == "create":
        target = sys.argv[2] if len(sys.argv) > 2 else "src/"
        print(f"📝 Creating tests for: {target}")
        print("💡 Use '/agents test-guardian' to generate comprehensive tests")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()