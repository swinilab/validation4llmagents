"""The vocabularies a VMX reference must resolve against (M2-metrics §1.2).

A reference resolves when it matches, character for character, a name declared
in the agent's own submission -- never the gold diagram -- so the metric measures
internal consistency, not similarity to gold.

The declared names are read with ModelsGrading's PlantUML parser, so both
modules agree on what a submission declares.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..ModelsGrading.parser import parse_behavioral, parse_structural
from ..ModelsGrading.parser.normalize import split_attribute

_STEREOTYPE = re.compile(r"<<[^>]*>>")
_VISIBILITY = re.compile(r"^[+\-#~]\s*")


def attribute_name(label_raw: str) -> str | None:
    """The name an attribute declaration introduces, as written.

    `name : String [0..1]` declares `name`. `String name` (type first) declares
    its last word. Visibility marks and stereotypes are not part of the name.
    """
    text = _VISIBILITY.sub("", _STEREOTYPE.sub(" ", label_raw).strip())
    head, _ = split_attribute(text)
    words = head.split()
    return words[-1] if words else None


def structural_vocab(result) -> set[str]:
    """Class names, enum names and `Class.attribute` of a parsed structural diagram."""
    names: set[str] = set()
    for element in result.elements:
        if element.kind in ("class", "enum"):
            names.add(element.label_raw)
        elif element.kind == "attribute":
            attribute = attribute_name(element.label_raw)
            if attribute:
                names.add(f"{element.fields['owner']}.{attribute}")
    return names


def behavioral_vocab(result) -> set[str]:
    """Action names of a parsed behavioral diagram, as declared."""
    return {element.label_raw for element in result.elements
            if element.kind == "action"}


def parse_vocab(path: Path, diagram: str, model_rules: dict) -> tuple[set[str], dict]:
    """Parse one submission diagram into its vocabulary plus a status block.

    A missing file has an empty vocabulary: nothing is declared, so every
    reference to it is broken. A file that does not parse cleanly still yields
    the names it did declare; its `validity` is recorded next to them.
    """
    if not path.is_file():
        return set(), {"status": "missing", "size": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    if diagram == "structural":
        result, build = parse_structural(text, model_rules), structural_vocab
    else:
        result, build = parse_behavioral(text, model_rules), behavioral_vocab
    names = build(result)
    return names, {"status": "parsed", "size": len(names),
                   "validity": round(result.validity(), 4),
                   "parse_error": result.parse_error}


def domain_vocab(path: Path, sections: list[str]) -> set[str]:
    """Requirement ids of the domain input file (keys of its id sections)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    for section in sections:
        block = data.get(section, {})
        if isinstance(block, dict):
            ids.update(block)
    return ids
