"""Label normalization (spec §5.4).

`label_raw` is preserved verbatim and used by the rule layer. `label_norm` is
used for embedding only. Never lowercase: role names and enum literals are
compared case-sensitively by the rule layer (§7.4.5).
"""

from __future__ import annotations

import re

_STEREOTYPE = re.compile(r"<<[^>]*>>")
_VISIBILITY = re.compile(r"^[+\-#~]\s*")
_TRAILING_TYPE = re.compile(r"\s*:\s*(?P<type>[^:]*)$")


def split_type_annotation(label: str) -> tuple[str, str | None]:
    """Split a trailing `: Type` annotation off a label (§5.4 step 2).

    Returns `(label_without_type, type_raw)`; `type_raw` is None when the label
    carries no annotation. A multiplicity suffix such as `String [0..1]` stays
    attached to the type, because the type table keys on the type name alone and
    the optionality is a separate fact the rule layer does not compare.
    """
    match = _TRAILING_TYPE.search(label)
    if match is None:
        return label.strip(), None
    type_raw = match.group("type").strip()
    head = label[: match.start()].strip()
    if not type_raw or not head:
        # `: ` with nothing either side is not an annotation; leave the label be.
        return label.strip(), None
    return head, type_raw


def normalize_label(label_raw: str, rules: dict) -> str:
    """Derive `label_norm` from `label_raw` (§5.4), in the specified order."""
    norm_cfg = rules["normalization"]
    text = label_raw
    if norm_cfg["strip_stereotypes"]:
        text = _STEREOTYPE.sub(" ", text)
    if norm_cfg["strip_visibility"]:
        text = _VISIBILITY.sub("", text.strip())
    text, _ = split_type_annotation(text)
    separators = norm_cfg["collapse_separators"]
    pattern = "[" + re.escape("".join(separators)) + r"\s]+"
    text = re.sub(pattern, " ", text)
    text = text.strip()
    if norm_cfg["lowercase"]:
        # The loader rejects `true` (§9.3); this branch exists so that the
        # setting is honoured rather than silently ignored if it is ever allowed.
        text = text.lower()
    return text


def normalize_type(type_raw: str | None) -> str | None:
    """`type_norm`: the bare type name, multiplicity and generics stripped."""
    if type_raw is None:
        return None
    text = type_raw.strip()
    text = re.sub(r"\[[^\]]*\]", " ", text)   # [0..1] optionality marker
    text = re.sub(r"<[^>]*>", " ", text)      # List<Foo> generics
    text = text.strip(" \t*?")
    return text or None
