"""Catalog-driven pytest orchestration for xverif.

Catalog imports are lazy so the stdlib-only environment checker can diagnose a
missing pytest/PyYAML/jsonschema bootstrap environment.
"""

from typing import Any

__all__ = ["Catalog", "CatalogError", "Suite"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .catalog import Catalog, CatalogError, Suite

        return {"Catalog": Catalog, "CatalogError": CatalogError, "Suite": Suite}[name]
    raise AttributeError(name)
