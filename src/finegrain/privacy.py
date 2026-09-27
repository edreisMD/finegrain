"""Conservative local filtering before any source reaches a teacher."""

import re

from .models import Memory, canonical

SECRET_PATTERNS = [
    r"\b(?:sk-|rv_|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{12,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"\bAKIA[A-Z0-9]{16}\b",
    r"(?i)\b(?:api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*['\"]?\S{8,}",
]


def has_secret(text: str) -> bool:
    return any(re.search(p, text) for p in SECRET_PATTERNS)


def rejection_reason(memory: Memory, tenant: str, max_chars: int) -> str | None:
    if memory.tenant != tenant:
        return "tenant_mismatch"
    if not memory.training_allowed:
        return "training_not_allowed"
    if memory.scope != "company":
        return "not_company_shared"
    if has_secret(canonical(memory.__dict__)):
        return "possible_secret"
    if len(memory.content) > max_chars:
        return "source_too_large"
    if len(memory.content.strip()) < 20:
        return "insufficient_content"
    return None
