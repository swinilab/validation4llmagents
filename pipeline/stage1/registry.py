"""Registry of the Stage 1 analysis modules.

Each module is usable three ways: from the command line, as an imported
function, and through this registry so it can be composed into a larger
pipeline without the caller knowing which module computes which metric.

A registry entry is a small, uniform wrapper: ``build(cfg)`` returns a callable
that takes the run's inputs and returns the metric payload. That keeps the
composition layer free of per-module argument handling.

**Why this lives here rather than in workflow_factory.py.** The repository's
``workflow_factory.build()`` constructs generation and validation components
through ``interfaces.base``; that module does not exist in this checkout, so
``workflow_factory`` cannot currently be imported at all. Rather than invent
an interface contract that would likely conflict with the real one, the
analysis modules register here, and ``workflow_factory`` can delegate to
:func:`build_stage1_analyzers` in one line once its own imports are fixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .config import Stage1Config, load_config

__all__ = [
    "ANALYZERS",
    "AnalyzerSpec",
    "build_analyzer",
    "build_stage1_analyzers",
    "available_metrics",
]


@dataclass(frozen=True)
class AnalyzerSpec:
    """One registered analysis module.

    Attributes:
        name: Registry key, also the module name.
        metric: The metric number this module computes.
        title: Human-readable metric name.
        build: Given a config, returns the callable that runs the module.
    """

    name: str
    metric: int
    title: str
    build: Callable[[Stage1Config], Callable[..., dict[str, Any]]]


def _build_parse_check(cfg: Stage1Config) -> Callable[..., dict[str, Any]]:
    """Return a bound parse_check runner."""
    from .parse_check import run_parse_check

    def run(
        run_id: str,
        diagrams: Sequence[str | Path],
        out_path: str | Path | None = None,
    ) -> dict[str, Any]:
        return run_parse_check(run_id, diagrams, out_path, cfg)

    return run


def _build_consistency(cfg: Stage1Config) -> Callable[..., dict[str, Any]]:
    """Return a bound consistency runner."""
    from .consistency import run_consistency

    def run(
        run_id: str,
        class_csv: str | Path,
        activity_csv: str | Path,
        requirements_csv: str | Path,
        out_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        return run_consistency(
            run_id, class_csv, activity_csv, requirements_csv, out_dir, cfg
        )

    return run


ANALYZERS: dict[str, AnalyzerSpec] = {
    "parse_check": AnalyzerSpec(
        name="parse_check",
        metric=7,
        title="Diagram Validity",
        build=_build_parse_check,
    ),
    "consistency": AnalyzerSpec(
        name="consistency",
        metric=8,
        title="Consistency",
        build=_build_consistency,
    ),
}


def available_metrics() -> dict[str, int]:
    """Registered module name -> metric number, sorted by name."""
    return {name: spec.metric for name, spec in sorted(ANALYZERS.items())}


def build_analyzer(
    name: str, cfg: Stage1Config | None = None
) -> Callable[..., dict[str, Any]]:
    """Instantiate one registered analyzer by name.

    Args:
        name: A key of :data:`ANALYZERS`.
        cfg: Effective config; loaded from ``config.yaml`` when None.

    Returns:
        The bound runner callable.

    Raises:
        KeyError: If no module is registered under that name.
    """
    if name not in ANALYZERS:
        raise KeyError(
            f"Unknown Stage 1 analyzer {name!r}. "
            f"Registered: {', '.join(sorted(ANALYZERS))}."
        )
    return ANALYZERS[name].build(cfg or load_config())


def build_stage1_analyzers(
    config: Mapping[str, Any] | str | Path | None = None,
) -> dict[str, Callable[..., dict[str, Any]]]:
    """Instantiate every registered analyzer.

    The entry point a pipeline factory calls. Accepts what the repository's
    factory already has to hand: a parsed ``pipeline_config.yaml`` mapping, a
    path to a config file, or None for the default.

    Args:
        config: A mapping holding a ``stage1`` section, a path to a config
            file, or None.

    Returns:
        Module name -> bound runner, for every registered analyzer.
    """
    if isinstance(config, Mapping):
        # A pipeline_config.yaml mapping: the stage1 settings may be nested
        # under 'stage1', in which case load_config applies them as overrides.
        from .config import load_config as _load

        section = config.get("stage1")
        cfg = _load(None, section if isinstance(section, Mapping) else None)
    elif config is None:
        cfg = load_config()
    else:
        cfg = load_config(config)
    return {name: spec.build(cfg) for name, spec in sorted(ANALYZERS.items())}
