"""
Custom exceptions for the GitHub Intelligence platform.
"""


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RepositoryNotFoundError(AppError):
    def __init__(self, message: str = "Repository not found"):
        super().__init__(message, status_code=404)


class InvalidURLError(AppError):
    def __init__(self, message: str = "Invalid repository URL"):
        super().__init__(message, status_code=400)


class CloneError(AppError):
    def __init__(self, message: str = "Failed to clone repository"):
        super().__init__(message, status_code=500)


class AnalysisError(AppError):
    def __init__(self, message: str = "Analysis failed"):
        super().__init__(message, status_code=500)


class AnalysisInProgressError(AppError):
    def __init__(self, message: str = "Analysis still in progress"):
        super().__init__(message, status_code=409)
