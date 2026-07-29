"""ef — build and serve experts over packs of code, docs, papers and notes."""

from __future__ import annotations

import os

#: The pack's graph output directory. graphify reads GRAPHIFY_OUT once at import
#: time (graphify.paths) and derives both the output leaf name and its
#: skip-directory set from it, so it has to be set before any graphify module is
#: imported. Every ef module is a submodule of this package, so this runs first.
GRAPH_DIR_NAME = "graph"
os.environ["GRAPHIFY_OUT"] = GRAPH_DIR_NAME


class EfError(Exception):
    """A condition the user can fix. The CLI prints it and exits non-zero."""


__all__ = ["GRAPH_DIR_NAME", "EfError"]
