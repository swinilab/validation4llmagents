"""staging.py -- copy a generated workspace's files under the names a grader expects.

The generated workspace is only read. Each grading evaluator stages the files it
needs into `<run dir>/grading/<module>/submission/`; a file the generator did not
produce is simply absent, which the module grades as missing rather than failing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Name patterns the generator may use for each diagram, first match wins.
DIAGRAM_PATTERNS = {
    "structural.puml": ("*structural*.puml", "*class*.puml"),
    "behavioral.puml": ("*behavioral*.puml", "*activity*.puml"),
}


def source_dir(workspace: Path) -> Path:
    """Where the generator put its artifacts: `artifacts/` if present."""
    artifacts = workspace / "artifacts"
    return artifacts if artifacts.is_dir() else workspace


def stage(workspace: Path, target: Path,
          wanted: dict[str, tuple[str, ...]]) -> Path:
    """Copy one file per entry of `wanted` into a fresh `target` directory.

    `wanted` maps the staged file name to glob patterns tried in order; the first
    pattern with a match supplies the file (first match by name).
    """
    source = source_dir(workspace)
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    for name, patterns in wanted.items():
        for pattern in patterns:
            found = sorted(source.glob(pattern))
            if found:
                shutil.copy2(found[0], target / name)
                break
    return target
