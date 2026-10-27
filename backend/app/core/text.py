"""Normalisation de texte et d'URL (matching, dédoublonnage)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PUNCT = re.compile(r"[^\w\s+#./-]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]+>")
_INLINE_TAGS = re.compile(r"(?i)</?(strong|b|em|i|u|span|a|small|code|abbr|mark|sup|sub)(\s[^>]*)?>")

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "gh_src",
    "lever-origin",
    "lever-source",
}


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = strip_accents(value.lower())
    value = _PUNCT.sub(" ", value)
    return _SPACES.sub(" ", value).strip()


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    import html

    text = html.unescape(value)
    text = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", text)
    text = _INLINE_TAGS.sub("", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def contains_phrase(haystack_norm: str, phrase: str) -> bool:
    """Recherche d'une expression normalisée avec frontières de mots (évite « r » dans « react »)."""
    needle = normalize_text(phrase)
    if not needle:
        return False
    return re.search(r"(?<![\w])" + re.escape(needle) + r"(?![\w])", haystack_norm) is not None


def normalize_url(url: str) -> str:
    """URL canonique : schéma/hôte en minuscules, sans fragment, sans paramètres de suivi,
    paramètres triés, sans « / » final, sans « www. »."""
    url = url.strip()
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k.lower() not in TRACKING_PARAMS)
    )
    return urlunsplit((scheme, host + port, path, query, ""))


def stable_hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def similarity(a: str, b: str) -> float:
    """Similarité de Jaccard sur les mots normalisés (0..1)."""
    ta, tb = set(normalize_text(a).split()), set(normalize_text(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
