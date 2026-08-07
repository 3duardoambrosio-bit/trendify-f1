from __future__ import annotations
import json, re
from typing import Any, Mapping, MutableMapping
from urllib.parse import unquote_plus, urlsplit, urlunsplit

SENSITIVE_KEYS = {"token","access_token","refresh_token","api_key","apikey","secret","password","authorization","bearer","client_secret","private_key","secret_key","credential","credentials"}
_SENSITIVE_URL_KEYS = {re.sub(r"[^a-z0-9]", "", key.lower()) for key in SENSITIVE_KEYS}
_URL_REDACTED = "REDACTED"
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
INVALID_URL_REDACTED = "<invalid-url-redacted>"
TOKEN_PATTERNS = [
  re.compile(r"EAABw[A-Za-z0-9]+"),
  re.compile(r"sk_live_[A-Za-z0-9]+"),
  re.compile(r"sk_test_[A-Za-z0-9]+"),
  re.compile(r"shpat_[A-Za-z0-9]+"),
  re.compile(r"shpss_[A-Za-z0-9]+"),
  re.compile(r"[a-f0-9]{32,}", re.IGNORECASE),
]

def looks_sensitive_string(s: str) -> bool:
  if not s: return False
  return any(p.search(s) for p in TOKEN_PATTERNS) or (len(s) >= 24 and (sum(c.isalnum() for c in s)/len(s)) >= 0.80)

def sanitize_for_log(value: Any, show_chars: int = 6) -> str:
  if value is None: return "***"
  if not isinstance(value, str): value = str(value)
  if looks_sensitive_string(value):
    prefix = value[:max(show_chars,0)]
    return f"{prefix}...***" if prefix else "***"
  return value

def redact_url(url: str) -> str:
  """Redact unsafe URL components while preserving safe diagnostics."""
  if not isinstance(url, str):
    return INVALID_URL_REDACTED

  try:
    parts = urlsplit(url)
    userinfo = parts.netloc.rsplit("@", 1)[0] if "@" in parts.netloc else ""
    netloc = parts.netloc.rsplit("@", 1)[-1]
    changed = netloc != parts.netloc or bool(parts.fragment)

    if _INVALID_PERCENT_ESCAPE.search(parts.query):
      query = _URL_REDACTED
      changed = True
    else:
      segments = re.split(r"([&;])", parts.query)
      redacted = []

      for segment in segments:
        if segment in {"&", ";"} or segment == "":
          redacted.append(segment)
          continue

        key = segment.split("=", 1)[0]
        normalized_key = re.sub(r"[^a-z0-9]", "", unquote_plus(key).lower())
        if any(sensitive_key in normalized_key for sensitive_key in _SENSITIVE_URL_KEYS):
          redacted.append(f"{key}={_URL_REDACTED}")
          changed = True
        else:
          redacted.append(segment)

      query = "".join(redacted)

    if _INVALID_PERCENT_ESCAPE.search(userinfo):
      changed = True
    if _INVALID_PERCENT_ESCAPE.search(parts.fragment):
      changed = True

    if not changed:
      return url

    return urlunsplit((
      parts.scheme,
      netloc,
      parts.path,
      query,
      "",
    ))
  except Exception:
    return INVALID_URL_REDACTED

def sanitize_dict(data: Any, depth: int = 0, max_depth: int = 6) -> Any:
  if depth > max_depth: return {"_truncated":"max depth reached"}
  if isinstance(data, Mapping):
    out: MutableMapping[str, Any] = {}
    for k,v in data.items():
      ks = str(k); kl = ks.lower()
      if any(sk in kl for sk in SENSITIVE_KEYS): out[ks] = "***REDACTED***"
      else: out[ks] = sanitize_dict(v, depth+1, max_depth)
    return out
  if isinstance(data, (list, tuple, set)):
    return [sanitize_dict(x, depth+1, max_depth) for x in data]
  if isinstance(data, str): return sanitize_for_log(data)
  return data

def safe_json_dumps(data: Any, **kwargs: Any) -> str:
  return json.dumps(sanitize_dict(data), default=str, **kwargs)
