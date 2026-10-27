from .base import Storage
from .github_release import GitHubReleaseStorage
from .local import LocalStorage

__all__ = ["Storage", "LocalStorage", "GitHubReleaseStorage"]
