"""CFG extraction package."""
from .detector import detect_format
from .binary_scraper import BinaryScraper, ext_role, ALL_EXTS, EXTENSION_ROLES
from .reference_resolver import resolve_references
from .project_walker import walk_project

__all__ = [
    "detect_format",
    "BinaryScraper",
    "ext_role",
    "ALL_EXTS",
    "EXTENSION_ROLES",
    "resolve_references",
    "walk_project",
]
