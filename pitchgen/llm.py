"""Thin Groq wrapper: JSON-mode chat with disk cache, retries and a fallback model."""
import hashlib
import json
import time

from . import config


class LLMError(RuntimeError):
    pass


_client = None


def is_available() -> bool:
    return bool(config.GROQ_API_KEY)


def _get_client():
    global _client
    if _client is None:
        if not is_available():
            raise LLMError("GROQ_API_KEY is not set. Add it to .env or the sidebar.")
        from groq import Groq
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def set_api_key(key: str):
    """Allow the UI to supply a key at runtime."""
    global _client
    config.GROQ_API_KEY = (key or "").strip()
    _client = None


def _cache_path(payload: dict):
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return config.CACHE_DIR / f"llm_{h}.json"


def chat_json(system: str, user: str, temperature: float = 0.2, max_tokens: int = 2500,
              model: str | None = None, use_cache: bool = True) -> dict:
    """Call the LLM and return parsed JSON. Raises LLMError on failure."""
    models = [model or config.GROQ_MODEL]
    if config.GROQ_FALLBACK_MODEL and config.GROQ_FALLBACK_MODEL not in models:
        models.append(config.GROQ_FALLBACK_MODEL)

    payload = {"s": system, "u": user, "t": temperature, "m": models[0]}
    cp = _cache_path(payload)
    if use_cache and cp.exists():
        return json.loads(cp.read_text())

    client = _get_client()
    last_err = None
    for m in models:
        for attempt in range(3):
            try:
                extra = {"reasoning_effort": "low"} if "gpt-oss" in m else {}
                resp = client.chat.completions.create(
                    model=m,
                    **extra,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                    temperature=temperature,
                    max_tokens=max_tokens + (4000 if extra else 0),
                    response_format={"type": "json_object"},
                )
                text = resp.choices[0].message.content
                data = json.loads(text)
                data.setdefault("_model", m)
                cp.write_text(json.dumps(data))
                return data
            except json.JSONDecodeError as e:
                last_err = e
            except Exception as e:  # network, rate limit, auth
                last_err = e
                msg = str(e).lower()
                if "401" in msg or "invalid api key" in msg:
                    raise LLMError("Groq rejected the API key (401).") from e
                if "429" in msg or "rate" in msg:
                    break  # go straight to fallback model
                time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"LLM call failed after retries: {last_err}")
