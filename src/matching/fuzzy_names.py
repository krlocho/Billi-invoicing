"""Fuzzy name matching utilities for reconciliation."""

from rapidfuzz import fuzz

# Common Spanish name variants that should match
SPANISH_NAME_ALIASES: dict[str, list[str]] = {
    "jose": ["josé", "pepe", "josef"],
    "francisco": ["paco", "fran", "francis", "curro", "pancho"],
    "manuel": ["manolo", "manu"],
    "antonio": ["toño", "toni", "tony"],
    "carmen": ["carmela", "menchu"],
    "dolores": ["lola", "loles", "loli"],
    "maria": ["maría", "mari"],
    "concepcion": ["concha", "conchi"],
    "mercedes": ["merche", "mercy"],
    "pilar": ["pili"],
    "rosario": ["charo", "rosi"],
    "fernando": ["nando", "fer"],
    "alejandro": ["alex", "álex"],
    "alberto": ["berto"],
    "rafael": ["rafa"],
    "miguel": ["migue"],
    "daniel": ["dani"],
    "david": ["davi"],
    "carlos": ["carlitos"],
    "pedro": ["peter"],
    "juan": ["juanito", "juancho"],
    "jesus": ["jesús", "chus", "suso"],
    "isabel": ["isa", "isabelita", "chabela"],
    "teresa": ["tere"],
}

# Build reverse lookup
_ALIAS_LOOKUP: dict[str, str] = {}
for canonical, aliases in SPANISH_NAME_ALIASES.items():
    _ALIAS_LOOKUP[canonical] = canonical
    for alias in aliases:
        _ALIAS_LOOKUP[alias] = canonical


def normalize_name(name: str) -> str:
    """Normalize a name for comparison."""
    import unicodedata

    name = name.lower().strip()
    # Remove accents
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name


def get_canonical_name(name: str) -> str:
    """Get the canonical form of a first name."""
    normalized = normalize_name(name)
    parts = normalized.split()
    canonical_parts = []
    for part in parts:
        canonical = _ALIAS_LOOKUP.get(part, part)
        canonical_parts.append(canonical)
    return " ".join(canonical_parts)


def name_similarity(name1: str | None, name2: str | None) -> float:
    """Compare two names with fuzzy matching and alias support.
    Returns a score between 0.0 and 1.0.
    """
    if not name1 or not name2:
        return 0.0

    # Direct fuzzy comparison
    direct_score = fuzz.token_sort_ratio(
        normalize_name(name1), normalize_name(name2)
    ) / 100.0

    # Canonical comparison (handles Jose vs Francisco etc.)
    canonical1 = get_canonical_name(name1)
    canonical2 = get_canonical_name(name2)
    canonical_score = fuzz.token_sort_ratio(canonical1, canonical2) / 100.0

    return max(direct_score, canonical_score)
