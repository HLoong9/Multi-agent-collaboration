"""Web Agent auth_scope compatibility helpers."""

from __future__ import annotations


def normalize_web_auth_scope(auth_scope: dict | None) -> dict:
    """Map legacy Orchestrator scope keys to PentestAgent scope keys."""
    normalized = dict(auth_scope or {})
    if "allowed_domains" not in normalized and normalized.get("allowed_hosts"):
        normalized["allowed_domains"] = list(normalized.get("allowed_hosts") or [])
    if "allowed_ip_ranges" not in normalized and normalized.get("allowed_cidrs"):
        normalized["allowed_ip_ranges"] = list(normalized.get("allowed_cidrs") or [])
    return normalized
