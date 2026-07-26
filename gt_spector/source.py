import enum
import re
from dataclasses import dataclass

class SourceKind(enum.Enum):
    FILE = "file"
    SHM = "shm"

@dataclass
class SourceSpec:
    kind: SourceKind
    path: str

def parse_source(s: str) -> SourceSpec:
    m = re.match(r"(file|shm)://(.+)", s)
    if not m:
        raise ValueError(f"Invalid source: {s}")
    return SourceSpec(SourceKind(m.group(1)), m.group(2))
