"""
LangGraph orchestration for the bot's agentic loop (Sec 4.1).

Pattern, per Technical PRD Sec 4.1: the LLM (Groq) receives tool schemas
on every call and decides contextually whether a tool is needed — there is
no separate router/classifier step run on every message. If it calls a
tool, the result is appended and a second call produces the final answer.

Built as a plain LangGraph StateGraph over MessagesState (the documented
"hello world" shape at docs.langchain.com/oss/python/langgraph/overview),
with two nodes (`agent`, `tools`) and one conditional edge — this keeps
the graph auditable without depending on prebuilt-agent abstractions
whose current import path we haven't independently verified against the
pinned langgraph version.

@traceable is applied to every node function, per the user's explicit
request, so each step shows up as its own span in LangSmith alongside the
graph-level trace LangGraph already emits when LANGSMITH_TRACING=true.

NOTE on message shape: LangGraph's `add_messages` reducer (used on
BotState.messages below) silently upgrades plain dicts into LangChain
BaseMessage objects (HumanMessage/AIMessage/ToolMessage/...) as they pass
through graph state. Groq's raw SDK has no knowledge of those objects and
requires flat {"role": ..., "content": ...} dicts. `_to_groq_dict` is the
single place that normalizes either shape into what Groq expects — every
node uses it instead of hand-rolling isinstance/getattr checks.

STREAMING: `run_turn_stream` below is a second entry point, used by the
SSE route in routes_bot.py, that yields progress as it happens instead of
returning one final string. It intentionally does NOT go through the
compiled LangGraph graph — LangGraph node functions return their whole
result at once, so streaming Groq token deltas out of a node isn't a
natural fit without wrapping every node in its own generator protocol.
Instead it drives the same agent/tool loop manually, one Groq
`stream=True` call at a time, yielding:
  {"type": "status", "tool": <name>}   - a tool call is about to run
  {"type": "token", "text": <chunk>}   - a piece of the final answer
  {"type": "final", "text": <full>}    - the complete final answer
`run_turn` (non-streaming) is left in place and unchanged for any other
caller that still wants a single awaited string.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, TypedDict

import litellm
from groq import (
    APIStatusError as GroqAPIStatusError,
    AsyncGroq,
    RateLimitError as GroqRateLimitError,
)
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langsmith import traceable
from app.observability.metrics import inference_tokens_total
from app.bot.web_search import search_web
from app.config import settings

_groq_client = AsyncGroq(api_key=settings.groq_api_key)

# HIGH AVAILABILITY FALLBACK: Groq is the primary generation provider, but
# its free-tier daily/TPM quota can be exhausted mid-session. When that
# happens, every call in this file transparently falls back to Cohere (via
# LiteLLM, reading COHERE_API_KEY from env) instead of failing the turn.
# This also means every eval harness script that calls run_turn /
# run_turn_stream (generator, agent, multi_turn, safety) gets the same
# fallback for free — no changes needed in those files.
#
# litellm.drop_params=True: Cohere's chat API doesn't support every
# OpenAI-style param LiteLLM might forward (e.g. response_format); this
# makes LiteLLM silently drop unsupported ones instead of raising.
litellm.drop_params = True

_FALLBACK_MODEL = (
    "cohere/command-a-03-2025"  # confirmed available/working on this Cohere account
)


def _is_groq_quota_error(exc: Exception) -> bool:
    """True for Groq rate-limit / quota-exhaustion errors specifically —
    NOT for other Groq errors (bad request, auth failure, etc.), which
    should still raise normally rather than silently falling back."""
    if isinstance(exc, GroqRateLimitError):
        return True
    if isinstance(exc, GroqAPIStatusError) and getattr(exc, "status_code", None) == 429:
        return True
    return False


async def _create_completion(
    *,
    messages: list[dict],
    tools: list[dict] | None,
    temperature: float,
    stream: bool = False,
    stream_options: dict | None = None,
):
    """Single entry point for every LLM call in this file. Tries Groq
    first; on a Groq quota/rate-limit error, falls back to Cohere via
    LiteLLM's acompletion, which returns an OpenAI-compatible response
    (or async chunk stream) shape — so all the existing
    message/tool_call parsing code below works unchanged regardless of
    which provider actually served the call.

    KNOWN LIMITATION: for streaming calls, this only catches a Groq
    quota error raised when the stream is FIRST created. If Groq accepts
    the call but then hits a quota error mid-stream (rarer, but possible
    under bursty TPM limits), that error propagates up rather than
    falling back — recovering mid-stream would mean discarding partial
    output and isn't handled here.
    """
    kwargs = {
        "model": settings.groq_model,
        "messages": messages,
        "tools": tools,
        "temperature": temperature,
    }
    if stream:
        kwargs["stream"] = True
        if stream_options:
            kwargs["stream_options"] = stream_options

    groq_kwargs = dict(kwargs)
    while True:
        try:
            return await _groq_client.chat.completions.create(**groq_kwargs)
        except TypeError as exc:
            # Installed groq SDK version doesn't support a param we
            # passed (seen with stream_options on some pinned versions)
            # — drop it and loop back to try Groq again (not a return,
            # so a rate-limit error on THIS retry still gets caught by
            # the except clause below rather than escaping uncaught).
            if "stream_options" not in str(exc) or "stream_options" not in groq_kwargs:
                raise
            print(
                f"[graph] Installed groq SDK rejected stream_options ({exc}); retrying without it."
            )
            groq_kwargs = {
                k: v for k, v in groq_kwargs.items() if k != "stream_options"
            }
            continue
        except (GroqRateLimitError, GroqAPIStatusError) as exc:
            if not _is_groq_quota_error(exc):
                raise
            print(
                f"[graph] Groq quota/rate-limit hit ({exc}); falling back to {_FALLBACK_MODEL}."
            )
            fallback_kwargs = {**kwargs, "model": _FALLBACK_MODEL}
            return await litellm.acompletion(**fallback_kwargs)


# ── Tool schemas (Groq's OpenAI-compatible tool-calling format) ──────────
# Sec 4.1 mentions "web search + 2-3 other tools". `web_search` is backed
# by app/bot/web_search.py (DuckDuckGo's free Instant Answer API by
# default — see that module for its real, honest limitations).
# `current_datetime` is fully real and needs no external call.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information not confidently known, e.g. "
                "a very specific or regional dish. Use sparingly — most "
                "recipe questions should be answered from your own knowledge. "
                "This tool only returns well-known instant-answer content "
                "(e.g. Wikipedia-style summaries) — it often returns nothing "
                "for very specific or obscure queries, which is inconclusive, "
                "not evidence the information doesn't exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_datetime",
            "description": "Get the current date and time (UTC).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _current_datetime_tool() -> str:
    return datetime.now(timezone.utc).isoformat()


_TOOL_IMPLEMENTATIONS = {
    "current_datetime": _current_datetime_tool,
    "web_search": search_web,  # async — see dispatch in tools_node below
}


class BotState(TypedDict):
    messages: Annotated[list, add_messages]


def _to_groq_dict(msg) -> dict:
    """Coerce a LangChain BaseMessage OR an already-plain dict into the
    flat {"role", "content", ...} shape Groq's raw SDK requires. Needed
    because LangGraph's `add_messages` reducer silently upgrades plain
    dicts into BaseMessage objects as they pass through graph state.
    Every node that reads state["messages"] should go through this
    instead of hand-checking isinstance/getattr."""
    if isinstance(msg, dict):
        return msg  # already plain — e.g. the dicts our own nodes build

    if isinstance(msg, BaseMessage):
        role_map = {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "tool": "tool",
        }
        role = role_map.get(msg.type, msg.type)
        out: dict = {"role": role, "content": msg.content or ""}
        # AIMessage may carry tool_calls in LangChain's own shape.
        if getattr(msg, "tool_calls", None):
            out["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in msg.tool_calls
            ]
        # ToolMessage carries tool_call_id.
        if getattr(msg, "tool_call_id", None):
            out["tool_call_id"] = msg.tool_call_id
        return out

    raise TypeError(f"Unexpected message type in state: {type(msg)}")


@traceable(name="bot_agent_node")
async def agent_node(state: BotState) -> dict:
    """Calls Groq with the current message list + tool schemas. Groq
    decides contextually whether to call a tool (Sec 4.1) — no separate
    classifier step runs first."""
    groq_messages = [_to_groq_dict(m) for m in state["messages"]]
    completion = await _create_completion(
        messages=groq_messages,
        tools=TOOLS,
        temperature=0.3,
    )
    message = completion.choices[0].message

    # Sec 5 — inference_tokens_total, labeled by model + direction.
    # completion.usage is populated on every non-streaming response,
    # whether served by Groq or the Cohere fallback (LiteLLM normalizes
    # this the same way). Label with whichever model actually served
    # the call (completion.model) rather than always settings.groq_model,
    # so fallback usage is attributed correctly.
    actual_model = getattr(completion, "model", None) or settings.groq_model
    usage = getattr(completion, "usage", None)
    if usage:
        inference_tokens_total.labels(model=actual_model, direction="prompt").inc(
            usage.prompt_tokens
        )
        inference_tokens_total.labels(model=actual_model, direction="completion").inc(
            usage.completion_tokens
        )

    # Normalize to the plain dict shape add_messages/MessagesState expect.
    msg_dict: dict = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        msg_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return {"messages": [msg_dict]}


@traceable(name="bot_tools_node")
async def tools_node(state: BotState) -> dict:
    """Executes any tool call(s) the agent node just requested and
    appends the result(s) as `role: tool` messages (item 7 of Sec 4.2's
    context-assembly ordering)."""
    last = _to_groq_dict(state["messages"][-1])
    tool_calls = last.get("tool_calls")

    results = []
    for call in tool_calls or []:
        name = call["function"]["name"]
        args = json.loads(call["function"]["arguments"] or "{}")
        impl = _TOOL_IMPLEMENTATIONS.get(name)
        if impl is None:
            output = f"[unknown tool: {name}]"
        elif inspect.iscoroutinefunction(impl):
            output = await impl(**args)
        else:
            output = impl(**args)
        results.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": output,
            }
        )
    return {"messages": results}


def _route_after_agent(state: BotState) -> str:
    last = _to_groq_dict(state["messages"][-1])
    return "tools" if last.get("tool_calls") else END


def build_graph():
    graph = StateGraph(BotState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent", _route_after_agent, {"tools": "tools", END: END}
    )
    # After a tool result is appended, go back to the agent for the second
    # call that produces the final answer (Sec 4.1's "second call").
    graph.add_edge("tools", "agent")
    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


@traceable(name="bot_turn")
async def run_turn(messages: list[dict]) -> str:
    """Entry point used by the bot API route: runs one full turn (agent
    call, optional tool round-trip, final answer) and returns the
    assistant's final text. Non-streaming — kept for any caller that
    wants a single awaited string instead of progress events."""
    result = await get_graph().ainvoke({"messages": messages})
    final_message = _to_groq_dict(result["messages"][-1])
    return final_message.get("content") or ""


@traceable(name="bot_turn_stream")
async def run_turn_stream(messages: list[dict]) -> AsyncGenerator[dict, None]:
    """Streaming entry point used by the SSE route. Drives the same
    agent/tool loop as build_graph(), but manually, one Groq
    `stream=True` call at a time, so token deltas can be yielded to the
    caller as they arrive rather than buffered until a node returns.

    Yields:
      {"type": "status", "tool": <name>}   before running a tool call
      {"type": "token", "text": <chunk>}   for each streamed content delta
      {"type": "final", "text": <full>}    once the final (non-tool-call)
                                            answer has finished streaming

    TOKEN METRICS: stream=True calls don't carry usage on normal chunks —
    stream_options={"include_usage": True} (OpenAI-compatible, Groq
    supports it) makes the LAST chunk of each stream carry a `usage`
    field instead. That chunk has choices=[] (no delta.content/tool_calls
    to process), so it's checked for and consumed separately from the
    normal per-chunk loop below, once per Groq stream call — i.e. once
    per agent turn, matching agent_node's non-streaming behavior of
    recording usage once per Groq call.
    """
    working_messages = list(messages)

    # Safety cap on agent<->tool round-trips — mirrors the implicit loop
    # in the compiled graph (agent -> tools -> agent -> ... -> END),
    # which has no explicit bound either, but a runaway tool-calling loop
    # should never hang a live SSE connection indefinitely.
    for _ in range(5):
        stream = await _create_completion(
            messages=working_messages,
            tools=TOOLS,
            temperature=0.3,
            stream=True,
            stream_options={"include_usage": True},
        )

        content_parts: list[str] = []
        # Tool-call deltas arrive fragmented across chunks, keyed by their
        # position in the (possibly multi-) tool_calls list — accumulate
        # by index the same way OpenAI-compatible streaming requires.
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in stream:
            # Safely check for usage attribute since fallback providers (like Cohere)
            # may yield chunks without a usage property.
            usage = getattr(chunk, "usage", None)
            if usage:
                chunk_model = getattr(chunk, "model", None) or settings.groq_model
                inference_tokens_total.labels(
                    model=chunk_model, direction="prompt"
                ).inc(usage.prompt_tokens)
                inference_tokens_total.labels(
                    model=chunk_model, direction="completion"
                ).inc(usage.completion_tokens)
            if not getattr(chunk, "choices", None):
                continue

            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content_parts.append(delta.content)
                yield {"type": "token", "text": delta.content}
            if getattr(delta, "tool_calls", None):
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    acc = tool_calls_acc.setdefault(
                        idx, {"id": None, "name": None, "arguments": ""}
                    )
                    if getattr(tc_delta, "id", None):
                        acc["id"] = tc_delta.id
                    if getattr(tc_delta, "function", None):
                        if getattr(tc_delta.function, "name", None):
                            acc["name"] = tc_delta.function.name
                        if getattr(tc_delta.function, "arguments", None):
                            acc["arguments"] += tc_delta.function.arguments

        full_content = "".join(content_parts)

        if not tool_calls_acc:
            yield {"type": "final", "text": full_content}
            return

        ordered_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        assistant_msg: dict = {"role": "assistant", "content": full_content}
        assistant_msg["tool_calls"] = [
            {
                "id": c["id"],
                "type": "function",
                "function": {"name": c["name"], "arguments": c["arguments"]},
            }
            for c in ordered_calls
        ]
        working_messages.append(assistant_msg)

        for call in ordered_calls:
            name = call["name"]
            yield {"type": "status", "tool": name}
            args = json.loads(call["arguments"] or "{}")
            impl = _TOOL_IMPLEMENTATIONS.get(name)
            if impl is None:
                output = f"[unknown tool: {name}]"
            elif inspect.iscoroutinefunction(impl):
                output = await impl(**args)
            else:
                output = impl(**args)
            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": output,
                }
            )
        # Loop again — the agent gets another streamed turn to respond
        # to the tool result(s), exactly like the "tools -> agent" edge
        # in the compiled graph.

    yield {"type": "final", "text": full_content if "full_content" in locals() else ""}
