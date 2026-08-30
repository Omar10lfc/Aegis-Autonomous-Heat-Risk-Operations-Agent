"""Input and output safety guardrails for Aegis.

Detects and prevents:
1. Direct prompt injection & system prompt extraction attacks.
2. Jailbreak personas (DAN, uncensored, roleplay evasion).
3. Delimiter hijacking & markup escaping.
4. Off-topic / out-of-domain queries (Aegis strictly serves temperature and heat-risk operations).
5. Harmful or destructive command injection attempts.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class GuardrailResult(NamedTuple):
    is_safe: bool
    category: str | None = None
    reason: str | None = None


# Patterns indicating prompt injection, instruction override, or jailbreak
INJECTION_PATTERNS = [
    # 1. Instruction override attempts
    r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|system|initial|your|safety)?\s*(?:instructions|prompts|rules|directives|safety\s*rules|filters|guardrails)\b",
    r"\bdisregard\s+(?:all\s+|any\s+)?(?:previous|prior|system|initial|your|safety)?\s*(?:instructions|prompts|rules|directives|safety\s*rules|filters|guardrails)\b",
    r"\bforget\s+(?:all\s+|any\s+)?(?:previous|prior|system|your)?\s*(?:instructions|prompts|rules|role|identity|training)\b",
    r"\bdo\s+not\s+follow\s+(?:previous|system|safety)\s+instructions\b",
    r"\bnew\s+instructions\s*:\s*",
    r"\boverride\s+(?:all\s+)?(?:system|safety|security)?\s*(?:prompt|instructions|directives|rules)\b",
    r"\bsystem\s+override\s*:\s*",
    r"\bbypass\s+(?:all\s+)?(?:fortyguard|safety|security|temperature|guardrail|filters?)\b",
    
    # 2. System prompt / secret extraction
    r"\b(?:reveal|output|print|show\s+me|show|display|leak|give\s+me|tell\s+me|dump|repeat)\s+(?:all\s+|the\s+|your\s+|internal\s+|hidden\s+|original\s+|developer\s+mode\s+|system\s+|master\s+|secret\s+|raw\s+|server\s+|environment\s+|llm\s+)*(?:system\s+)?(?:prompt|instructions|system_prompt|api[_\s]?keys?|secrets?|credentials?|keys?|tokens?|passwords?|database\s+schema)\b",
    r"\bwhat\s+(?:is|are)\s+(?:all\s+|the\s+|your\s+|our\s+)*(?:original\s+|initial\s+|system\s+|core\s+|hidden\s+)*(?:system\s+)?(?:instructions|prompt|system_prompt|rules|api\s+keys?)\b",
    r"\brepeat\s+(?:the\s+)?text\s+(?:above|before)\b",
    r"\bcat\s+/etc/(?:passwd|shadow)\b",
    
    # 3. Jailbreak personas and modes
    r"\byou\s+are\s+now\s+(?:in\s+)?(?:dan|jailbreak|unrestricted|uncensored|developer\s+mode|chaos\s+mode)\b",
    r"\bact\s+as\s+(?:an?\s+)?(?:evil|unfiltered|uncensored|jailbroken|rogue|malicious|unrestricted)\b",
    r"\b(?:roleplay|assume\s+the\s+persona)\s+(?:as|of)\s+(?:an?\s+)?(?:malicious|hacker|evil|rogue|unrestricted|ai)\b",
    r"\bdo\s+anything\s+now\b",
    r"\bhypothetical\s+scenario\s+where\s+you\s+have\s+no\s+(?:rules|limits|safety|filters)\b",
    
    # 4. Delimiter hijacking / LLM control tokens / Markdown blocks
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"<<SYS>>",
    r"<</SYS>>",
    r"```\s*system",
    r"\[SYSTEM\]",
    r"\[/SYSTEM\]",
    r"###\s*(?:system|instruction)\s*:",
    r"---+\s*(?:BEGIN|START)\s+SYSTEM",
    
    # 5. Dangerous code & SQL/Shell injection
    r"<\s*script\b",
    r"javascript\s*:",
    r"\b(?:os\.system|subprocess\.Popen|eval\s*\(|exec\s*\(|__import__\s*\(|os\.environ)\b",
    r"\bDROP\s+TABLE\b",
    r"\bUNION\s+SELECT\b",
]

# Keywords indicating on-topic relevance to heat-risk and environmental operations
# Checked using whole-word boundary matching to prevent sub-word false positives (e.g. 'hot' in 'photograph')
HEAT_RISK_KEYWORDS = [
    r"\bheat\b",
    r"\bheats\b",
    r"\bheated\b",
    r"\bheating\b",
    r"\btemperature\b",
    r"\btemperatures\b",
    r"\btemp\b",
    r"\btemps\b",
    r"\bcelsius\b",
    r"\bfahrenheit\b",
    r"\bhot\b",
    r"\bhotter\b",
    r"\bhottest\b",
    r"\bcold\b",
    r"\bthreshold\b",
    r"\bthresholds\b",
    r"\bexceed\b",
    r"\bexceeded\b",
    r"\bexceeding\b",
    r"\bexceedance\b",
    r"\bpersist\b",
    r"\bpersisted\b",
    r"\bpersisting\b",
    r"\bpersistence\b",
    r"\bsustained\b",
    r"\bambient\b",
    r"\bweather\b",
    r"\bclimate\b",
    r"\bthermal\b",
    r"\bdegrees\b",
    r"\broute\b",
    r"\broutes\b",
    r"\breroute\b",
    r"\brerouting\b",
    r"\blogistics\b",
    r"\bsupply\s+chain\b",
    r"\bdelivery\b",
    r"\btruck\b",
    r"\btrucks\b",
    r"\bfleet\b",
    r"\byard\b",
    r"\byards\b",
    r"\bdepot\b",
    r"\bdepots\b",
    r"\bcrossdock\b",
    r"\bcross-dock\b",
    r"\bwarehouse\b",
    r"\bwarehouses\b",
    r"\bfacility\b",
    r"\bfacilities\b",
    r"\bdistribution\b",
    r"\bparcel\b",
    r"\bcargo\b",
    r"\bfreight\b",
    r"\binsurance\b",
    r"\bunderwriting\b",
    r"\bunderwrite\b",
    r"\bclaim\b",
    r"\bcoverage\b",
    r"\breal\s+estate\b",
    r"\bproperty\b",
    r"\bportfolio\b",
    r"\burban\b",
    r"\bcool\b",
    r"\bcooling\b",
    r"\bisland\b",
    r"\bphoenix\b",
    r"\btempe\b",
    r"\bmesa\b",
    r"\bscottsdale\b",
    r"\bglendale\b",
    r"\bchandler\b",
    r"\bfortyguard\b",
    r"\baoi\b",
    r"\bpolygon\b",
    r"\bsnapshot\b",
]


def check_prompt_injection(text: str) -> GuardrailResult:
    """Scan text for known prompt injection patterns and jailbreak attempts."""
    clean_text = text.strip()
    
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            return GuardrailResult(
                is_safe=False,
                category="prompt_injection",
                reason=f"Detected potential prompt injection / instruction override pattern: '{match.group(0)}'",
            )
    
    return GuardrailResult(is_safe=True)


def check_domain_relevance(text: str) -> GuardrailResult:
    """Verify that the brief is within Aegis's heat-risk operational domain using whole-word matching."""
    clean_text = text.lower().strip()
    
    # Must have at least 1 whole-word keyword matching heat, weather, geography, or logistics/insurance ops
    has_domain_keyword = any(re.search(pattern, clean_text, re.IGNORECASE) for pattern in HEAT_RISK_KEYWORDS)
    
    if not has_domain_keyword:
        return GuardrailResult(
            is_safe=False,
            category="off_topic",
            reason=(
                "Query is outside the scope of Aegis. Aegis is specialized strictly for "
                "street-level heat-risk intelligence, operations routing, and FortyGuard temperature analysis. "
                "Please submit an operational brief related to heat thresholds, route risk, facility temperature, or persistence."
            ),
        )
    
    return GuardrailResult(is_safe=True)


def validate_brief_guardrails(brief: str) -> GuardrailResult:
    """Full guardrail scan covering prompt injection, jailbreaks, and domain relevance."""
    if not brief or len(brief.strip()) < 8:
        return GuardrailResult(
            is_safe=False,
            category="empty_or_short",
            reason="Brief is too short. Please provide a clear operations brief (at least 8 characters).",
        )
    
    # Check 1: Prompt injection & adversarial safety (highest priority)
    inj_result = check_prompt_injection(brief)
    if not inj_result.is_safe:
        return inj_result
    
    # Check 2: Domain scope & relevance
    domain_result = check_domain_relevance(brief)
    if not domain_result.is_safe:
        return domain_result
    
    return GuardrailResult(is_safe=True)
