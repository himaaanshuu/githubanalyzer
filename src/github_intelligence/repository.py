"""
Git repository management for the GitHub Intelligence Engine.

This module is responsible for validating GitHub repository URLs,
cloning repositories, and handling Git-related failures.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from .config import CONFIG
from .exceptions import (
    InvalidRepositoryError,
    RepositoryCloneError,
)

logger = logging.getLogger(__name__)


class RepositoryManager:
    """
    Handles GitHub repository operations.

    The class isolates Git-related functionality from the rest of the
    application, following the separation-of-concerns principle.
    """

    def __init__(self, base_directory: Path | None = None) -> None:
        """
        Initialize the repository manager.

        Args:
            base_directory:
                Directory in which repositories will be stored.
                If omitted, the application configuration is used.
        """

        self.base_directory = (
            base_directory or CONFIG.repositories_dir
        )

    def clone(self, repository_url: str) -> Path:
        """
        Clone a GitHub repository using a shallow Git clone.

        Args:
            repository_url:
                HTTPS URL of the GitHub repository.

        Returns:
            Path to the cloned repository.

        Raises:
            InvalidRepositoryError:
                If the repository URL is invalid.

            RepositoryCloneError:
                If the cloning operation fails.
        """

        # Validate the URL before performing any external operation.
        self._validate_github_url(repository_url)

        # Extract a safe directory name from the repository URL.
        repository_name = self._extract_repository_name(
            repository_url
        )

        destination = self.base_directory / repository_name

        # Prevent accidental overwriting of an existing repository.
        if destination.exists():
            raise RepositoryCloneError(
                f"Repository already exists: {destination}"
            )

        # Create the parent directory if it does not already exist.
        self.base_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            "git",
            "clone",

            # We initially need the current source tree, not the
            # complete Git history.
            "--depth",
            "1",

            repository_url,
            str(destination),
        ]

        logger.info(
            "Cloning repository: %s",
            repository_url,
        )

        try:
            subprocess.run(
                command,
                check=True,
                timeout=CONFIG.git_timeout_seconds,
                capture_output=True,
                text=True,
            )

        except subprocess.TimeoutExpired as exc:
            raise RepositoryCloneError(
                "Repository cloning timed out."
            ) from exc

        except subprocess.CalledProcessError as exc:
            error_message = (
                exc.stderr.strip()
                if exc.stderr
                else "Unknown Git error."
            )

            raise RepositoryCloneError(
                f"Git clone failed: {error_message}"
            ) from exc

        logger.info(
            "Repository successfully cloned to: %s",
            destination,
        )

        return destination

    @staticmethod
    def _validate_github_url(repository_url: str) -> None:
        """
        Validate that the supplied URL belongs to GitHub.

        Only HTTPS GitHub URLs are accepted.
        """

        parsed_url = urlparse(repository_url)

        if parsed_url.scheme != "https":
            raise InvalidRepositoryError(
                "Only HTTPS repository URLs are supported."
            )

        if parsed_url.netloc.lower() != "github.com":
            raise InvalidRepositoryError(
                "Only GitHub repositories are supported."
            )

        if not parsed_url.path.strip("/"):
            raise InvalidRepositoryError(
                "Repository URL does not contain a repository path."
            )

    @staticmethod
    def _extract_repository_name(repository_url: str) -> str:
        """
        Extract the repository name from a GitHub URL.
        """

        repository_name = (
            urlparse(repository_url)
            .path
            .rstrip("/")
            .split("/")[-1]
        )

        # Git URLs commonly end with '.git'.
        if repository_name.endswith(".git"):
            repository_name = repository_name[:-4]

        if not repository_name:
            raise InvalidRepositoryError(
                "Unable to determine repository name."
            )

        return repository_name