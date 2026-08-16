"""
Application configuration for the GitHub Intelligence Engine.

Keeping configuration in one place prevents hard-coded values from
being scattered throughout the application.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """
    Immutable application configuration.

    Attributes:
        repositories_dir: Directory where cloned repositories are stored.
        git_timeout_seconds: Maximum time allowed for a Git operation.
    """

    repositories_dir: Path = Path("repositories")
    git_timeout_seconds: int = 120


CONFIG = AppConfig()