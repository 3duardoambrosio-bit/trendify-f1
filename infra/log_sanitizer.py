from __future__ import annotations
import json, re
from typing import Any, Mapping, MutableMapping

SENSITIVE_KEYS = {"token","access_token","refresh_token","api_key","apikey","secret","password","authorization","bearer","client_secret","private_key","secret_key","credential","credentials"}
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