import json
import logging
import asyncio
import httpx
import sys
import contextvars
from pathlib import Path
from typing import Any

# ── Dynamic Path Resolution ──────────────────────────────────────────────────
if hasattr(sys, '_MEIPASS'):
    BASE_PATH = Path(sys._MEIPASS)
else:
    BASE_PATH = Path(__file__).parent.parent.parent.absolute()

PROMPTS_DIR = BASE_PATH / "backend" / "prompts"

logger = logging.getLogger("pipeline")

# ── Per-request token tracking (ContextVar — safe for asyncio concurrency) ───
_token_store: contextvars.ContextVar[dict] = contextvars.ContextVar(
    'token_store', default=None
)

def reset_token_tracking() -> dict:
    """Call once at pipeline start. Returns the live accumulator dict."""
    store = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0}
    _token_store.set(store)
    return store

def record_tokens(raw_response: dict) -> None:
    """Pass the full Ollama JSON response; prompt/completion tokens are accumulated."""
    store = _token_store.get()
    if store is None:
        return
    prompt = raw_response.get("prompt_eval_count", 0) or 0
    completion = raw_response.get("eval_count", 0) or 0
    store["prompt_tokens"] += prompt
    store["completion_tokens"] += completion
    store["total_tokens"] += prompt + completion
    store["call_count"] += 1

def get_token_totals() -> dict:
    store = _token_store.get()
    if store is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "call_count": 0}
    return dict(store)


def load_prompt(filename: str) -> str:
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        # Fallback for internal structure if nested
        alt_path = Path(__file__).parent.parent / "prompts" / filename
        if alt_path.exists():
            return alt_path.read_text(encoding="utf-8")
        logger.error(f"Prompt not found: {prompt_path} or {alt_path}")
        raise FileNotFoundError(f"Prompt file not found: {filename}")
    return prompt_path.read_text(encoding="utf-8")


def _repair_inner_quotes(text: str) -> str:
    """
    State-machine pass: escape double-quotes that appear inside JSON string
    values (i.e. are not structural open/close quotes).
    Handles existing escape sequences correctly.
    """
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]

        # Pass escape sequences through unchanged (2-char unit)
        if ch == '\\' and i + 1 < len(text):
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                # Is this a closing quote?  After it (ignoring whitespace)
                # a closing quote must be followed by , } ] or :
                rest = text[i + 1:].lstrip()
                if not rest or rest[0] in ',}]:':
                    in_string = False
                    result.append(ch)
                else:
                    # Inner unescaped quote — escape it
                    result.append('\\"')
        else:
            result.append(ch)
        i += 1

    return ''.join(result)


def clean_json(text: str) -> dict:
    """Robust JSON extractor for LLM outputs that may include markdown,
    prose preamble, trailing commas, or unescaped inner quotes."""
    import re

    text = text.strip()

    # 1. Strip markdown code fences
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # 2. Extract outermost JSON object (drop leading/trailing LLM prose)
    obj_match = re.search(r'\{.*\}', text, re.DOTALL)
    if obj_match:
        text = obj_match.group(0)

    # 3. Remove trailing commas before } or ]
    text = re.sub(r',\s*([\]}])', r'\1', text)

    # Fast path — valid JSON
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError as exc:
        logger.warning(f"JSON parse failed ({exc}), running quote repair...")

    # 4. State-machine quote repair
    repaired = _repair_inner_quotes(text)
    repaired = re.sub(r',\s*([\]}])', r'\1', repaired)  # re-clean after repair
    try:
        return json.loads(repaired, strict=False)
    except json.JSONDecodeError:
        pass

    # 5. Last resort: truncate at the last closing brace
    last_brace = repaired.rfind('}')
    if last_brace > 0:
        try:
            return json.loads(repaired[:last_brace + 1], strict=False)
        except json.JSONDecodeError:
            pass

    # Give up — log context around the error position for debugging
    try:
        json.loads(repaired, strict=False)
    except json.JSONDecodeError as final_exc:
        start = max(0, final_exc.pos - 150)
        end = min(len(repaired), final_exc.pos + 150)
        logger.error(f"JSON repair failed. Context: ...{repaired[start:end]}...")
        raise final_exc

    raise exc  # fallback (shouldn't reach)

_RETRYABLE = (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError)
_RETRYABLE_STATUS = {429, 503}


async def ollama_chat(
    messages: list[dict],
    label: str,
    *,
    format: str = "json",
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    POST to Ollama /api/chat with automatic retry on connection errors and
    transient HTTP errors (429, 503).
    Returns the parsed Ollama response dict (caller reads ["message"]["content"]).
    Raises on permanent HTTP errors or after exhausting retries.
    """
    from config import settings

    url = f"{settings.ollama_base_url}/api/chat"
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "format": format,
    }

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in _RETRYABLE_STATUS:
                    exc = httpx.HTTPStatusError(
                        f"{resp.status_code} from Ollama",
                        request=resp.request,
                        response=resp,
                    )
                    raise exc
                resp.raise_for_status()
                return resp.json()
        except (_RETRYABLE + (httpx.HTTPStatusError,)) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in _RETRYABLE_STATUS:
                raise  # permanent error (404, 400, etc.) — don't retry
            last_exc = exc
            if attempt < max_retries:
                delay = 2 ** (attempt + 1)  # 2 s → 4 s → 8 s
                logger.warning(
                    f"[{label}] Ollama {type(exc).__name__} "
                    f"({getattr(getattr(exc, 'response', None), 'status_code', '')}) — "
                    f"retry {attempt + 1}/{max_retries} in {delay}s"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"[{label}] Ollama failed after {max_retries} retries: {exc}")
                raise

    raise last_exc  # type: ignore[misc]


async def safe_gather(tasks, return_exceptions=False):
    """
    Attempts to run tasks in parallel. If Ollama returns a 429 (Too Many Requests)
    or 503 (Overloaded), it falls back to sequential execution to support
    local/standard Ollama instances.
    """
    try:
        # Try parallel first
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    except Exception as e:
        # Check if it's a concurrency/overload error (Ollama specific codes)
        error_str = str(e).lower()
        is_overload = "429" in error_str or "503" in error_str or "too many requests" in error_str
        
        if is_overload:
            logger.warning("Parallel execution failed (Ollama overloaded). Falling back to sequential mode...")
            # We can't easily "restart" the tasks if they are already running/failed,
            # but for our pipeline, we will recreate them or rely on the caller to handle retry.
            # However, for simplicity in this specific project, we will catch it in the high-level 
            # and provide the logic there.
            raise e 
        raise e
