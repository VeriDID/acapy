"""Pytest fixtures and configuration."""

import subprocess
from pathlib import Path

import pytest
from pytest import Session

EXAMPLES_DIR = Path(__file__).parent / "examples"


class ExampleFailedException(Exception):
    """Raised when an example fails."""

    def __init__(self, message: str, exit_status: int):
        """Initialize ExampleFailedException."""

        super().__init__(message)
        self.exit_status = exit_status


class ExampleRunner:
    """Run the docker compose of a given example."""

    def __init__(self, compose_file: str):
        """Initialize ExampleRunner."""

        self.compose_file = compose_file

    def compose(self, *command: str) -> int:
        """Runs docker compose using subprocess with the given command.

        Returns exit status and output.
        """
        try:
            subprocess.run(
                ["docker", "compose", "-f", self.compose_file, *command],
                check=True,
            )
            return 0
        except subprocess.CalledProcessError as e:
            return e.returncode

    def cleanup(self):
        """Runs docker compose down -v for cleanup."""
        exit_status = self.compose("down", "-v")
        if exit_status != 0:
            raise ExampleFailedException(
                f"Cleanup failed with exit status {exit_status}", exit_status
            )

    def capture_logs(self):
        """Capture docker compose logs for debugging."""
        print("\n" + "=" * 80)
        print("CONTAINER LOGS ON FAILURE")
        print("=" * 80)
        for service in ["kanon-postgres", "bob", "wallet-db", "tails", "example"]:
            print(f"\n--- {service} logs ---")
            try:
                result = subprocess.run(
                    ["docker", "compose", "-f", self.compose_file, "logs", service, "--tail=500"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                print(result.stdout)
                if result.stderr:
                    print(f"STDERR: {result.stderr}")
            except Exception as e:
                print(f"Failed to get logs for {service}: {e}")
        print("=" * 80 + "\n")

    def handle_run(self, *command: str):
        """Handles the run of docker compose/.

        raises exception if exit status is non-zero.
        """
        failed = False
        exit_status = 0
        try:
            exit_status = self.compose(*command)
            if exit_status != 0:
                failed = True
        finally:
            if failed:
                self.capture_logs()
            self.cleanup()

        if failed:
            raise ExampleFailedException(
                f"Command failed with exit status: {exit_status}",
                exit_status=exit_status,
            )


def pytest_collect_file(parent: Session, file_path: Path):
    """Pytest collection hook.

    This will collect the docker compose.yml files from the examples and create
    pytest items to run them.
    """
    file = Path(str(file_path))

    # Skip certain examples
    if (file.parent / "__skip__").exists():
        return

    if file.suffix == ".yml" and file.parent.parent == EXAMPLES_DIR:
        return ExampleFile.from_parent(parent, path=file.parent)


class ExampleFile(pytest.File):
    """Pytest file for example."""

    def collect(self):
        """Collect tests from example file."""
        path = Path(self.fspath)
        item = ExampleItem.from_parent(
            self, name=path.name, compose_file=str(path / "docker-compose.yml")
        )
        item.add_marker(pytest.mark.examples)
        yield item


class ExampleItem(pytest.Item):
    """Example item.

    Runs the docker-compose.yml file of the example and reports failure if the
    exit status is non-zero.
    """

    def __init__(self, name: str, parent: pytest.File, compose_file: str):
        """Initialize ExampleItem."""
        super().__init__(name, parent)
        self.compose_file = compose_file

    def runtest(self) -> None:
        """Run the test."""
        ExampleRunner(self.compose_file).handle_run("run", "example")

    def repr_failure(self, excinfo):
        """Called when self.runtest() raises an exception."""
        if isinstance(excinfo.value, ExampleFailedException):
            return "\n".join(
                [
                    "Example failed!",
                    f"    {excinfo.value}",
                ]
            )
        return f"Some other exception happened: {excinfo.value}"

    def reportinfo(self):
        """Report info about the example."""
        return self.fspath, 0, f"example: {self.name}"
