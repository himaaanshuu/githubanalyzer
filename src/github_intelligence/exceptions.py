"""
Custom exceptions for the GitHub Intelligence Engine.

The purpose of this module is to provide meaningful, application-level
errors instead of exposing low-level implementation details throughout
the codebase.
"""


class RepositoryError(Exception):
    """
    Base exception for all repository-related errors.

    All repository-specific exceptions inherit from this class so that
    higher-level application code can handle repository failures with
    a single exception type when necessary.
    """


class InvalidRepositoryError(RepositoryError):
    """
    Raised when a repository URL or repository state is invalid.
    """


class RepositoryCloneError(RepositoryError):
    """
    Raised when a Git repository cannot be cloned successfully.
    """