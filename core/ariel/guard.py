import json
import logging

def sanitize(user_input: str):
    """Very simple sanitization that removes suspicious patterns.
    Returns sanitized input and a flag indicating whether a warning was triggered.
    """
    suspicious = ["<script", "</script>", "$(", "`", "${", ";", "&&", "|", "'", '"']
    lowered = user_input.lower()
    warning = any(sig in lowered for sig in suspicious)
    # Very naive removal – just strip the patterns
    safe = user_input
    for sig in suspicious:
        safe = safe.replace(sig, "")
    return safe, warning

class ArielGuard:
    def sanitize(self, user_input: str):
        return sanitize(user_input)
