"""
Shared DeepEval concurrency settings, used by every evaluate() call
across the harness.

Judge: Cohere (command-a-03-2025, LiteLLM's resolved default for
cohere/command-r-plus on this account) via LiteLLM, reading
COHERE_API_KEY from env
(`deepeval set-litellm --model=cohere/command-r-plus --prompt-api-key --save`).

Trial key hard cap: 20 API calls/minute. Each DeepEval test case can
fire several judge calls internally (Contextual Precision/Recall
generate one verdict per retrieved chunk, plus a reasoning call), so
throttling must account for that — not just test-case count.

Previously tried and abandoned:
- Groq: free-tier TPM as low as 8000, exhausted quickly.
- Gemini: fresh Google Cloud project got 403 PERMISSION_DENIED — a
  known, unresolved Google-side free-tier restriction.
- Cerebras: both models on the account (qwen-3.8-27b, gpt-oss-120b)
  returned "payment_required" — free tier not available on this
  account/region.
"""

import json
import os

import litellm
from deepeval.evaluate.configs import AsyncConfig

litellm.drop_params = True


# ── Lenient JSON parsing for the Cohere judge ─────────────────────────
# Cohere's chat models (command-a-03-2025 here) aren't run in a strict
# JSON-only response mode by DeepEval's LiteLLM wrapper, so they
# sometimes emit a valid JSON object followed by trailing text (an
# extra newline, a stray sentence, etc). DeepEval's own parser
# (deepeval.models.llms.utils.trim_and_load_json) uses plain
# json.loads(), which raises "Extra data" the instant anything follows
# the JSON — even whitespace-adjacent junk.
#
# json.JSONDecoder().raw_decode() parses just the first valid JSON
# value from the string and ignores everything after it, which is
# exactly the tolerance we need. We patch the name INSIDE
# deepeval.models.llms.litellm_model, because that module calls
# trim_and_load_json(...) as an unqualified name bound in its own
# namespace at import time (`from .utils import trim_and_load_json`) —
# patching deepeval.models.llms.utils.trim_and_load_json instead would
# not affect that already-bound reference.
def _lenient_trim_and_load_json(json_str: str):
    text = json_str.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        obj, _end_index = json.JSONDecoder().raw_decode(text)
        return obj
    except json.JSONDecodeError:
        # Fall back to DeepEval's own implementation (handles a couple
        # of edge cases like stray leading text) so we don't lose any
        # of its existing recovery behavior — just add ours on top.
        from deepeval.models.llms.utils import trim_and_load_json as _original

        return _original(json_str)


try:
    import deepeval.models.llms.litellm_model as _litellm_model_mod

    _litellm_model_mod.trim_and_load_json = _lenient_trim_and_load_json
except ImportError:
    # DeepEval version doesn't have this module under this path — skip
    # the patch rather than breaking the whole harness on import.
    pass

# Let DeepEval wait out a 429 and retry with a long backoff, since
# Cohere trial's 20/min cap means bursts will hit it regardless of
# throttling below.
os.environ.setdefault("DEEPEVAL_RETRY_MAX_ATTEMPTS", "20")
os.environ.setdefault("DEEPEVAL_RETRY_CAP_SECONDS", "90")
os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "180"

EVAL_ASYNC_CONFIG = AsyncConfig(
    run_async=True,
    max_concurrent=1,  # one test case's judge calls in flight at a time
    throttle_value=35,  # generous gap — each test case can itself burn several calls
)
