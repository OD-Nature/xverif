from __future__ import annotations

import pytest

from .catalog import Suite


def apply_xdist_resource_group(item: pytest.Item, suite: Suite) -> None:
    tokens = {str(value) for value in suite.resources.get("tokens", [])}
    # NPI libraries and the underlying Verdi databases can be used from child
    # processes but are not a freely parallel resource on the supported host. Derive
    # the common token from the capability so every suite with identical
    # semantics receives the same scheduling contract, even when its catalog
    # entry does not need any suite-specific resource metadata.
    if "npi" in suite.capabilities:
        tokens.add("verdi_npi")
    if not tokens:
        return
    # loadgroup keeps all suites that claim the same normalized token set on one
    # worker, providing deterministic serialization without replacing xdist.
    group = "xverif-resource-" + "-".join(sorted(tokens))
    item.add_marker(pytest.mark.xdist_group(name=group))
