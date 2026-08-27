import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Encode un objet de manière stable, indépendante de l'ordre des clés."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
