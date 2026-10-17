"""SensOS Messaging Plane (MP, provisional name) - stage MP0: profile schemas and test vectors.

MP adds no storage format. A message is a HEXT v2 ``source``; a readback and an alignment are HEXT v2
``annotation`` documents. The MP-specific fields live in a profile payload carried as one ``evidence``
item (``format`` = profile id, ``body`` = RFC 8785 text of the payload). See docs/mp/MP0.md.
"""

from sensos_core.mp.profile import (
    PROFILES,
    MPError,
    check_envelope,
    check_references,
    find_floats,
    load_schema,
    loads_strict,
    validate_payload,
)

__all__ = [
    "PROFILES",
    "MPError",
    "check_envelope",
    "check_references",
    "find_floats",
    "load_schema",
    "loads_strict",
    "validate_payload",
]
