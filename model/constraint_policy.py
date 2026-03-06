from enum import Enum

class ConstraintPolicy(str, Enum):
    MANDATORY = "MANDATORY"     # constraint twardy (musi być spełniony)
    PREFERRED = "PREFERRED"     # soft – jeśli możliwe
    DISABLED = "DISABLED"       # wyłączony