"""
Assembles the context sent to Groq for one turn, in the exact order
specified by Technical PRD Sec 4.2:

  1. System prompt
  2. Tool schemas         (handled by graph.py passing `tools=` to Groq)
  3. user.md              (persistent cross-session memory)
  4. Conversation history (rolling-block summarized, Sec 4.3)
  5. RAG doc context      (only if the user opted in this session)
  6. Current user message
  7. Tool result          (only appended if a tool was invoked this turn)
"""

from __future__ import annotations

from app.bot.history_summarizer import build_context_messages
from app.bot.prompts.system_prompt import SYSTEM_PROMPT


def assemble_messages(
    *,
    user_memory_md: str,
    raw_messages: list[dict],
    block_summaries: dict[int, str],
    rag_context: str | None,
    current_user_message: str,
) -> list[dict]:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 3. user.md — persistent cross-session memory.
    if user_memory_md:
        messages.append(
            {
                "role": "system",
                "content": f"What you remember about this user from past sessions:\n{user_memory_md}",
            }
        )

    # 4. Conversation history, summarized per the rolling-block scheme.
    messages.extend(build_context_messages(raw_messages, block_summaries))

    # 5. Optional RAG doc context — only if the user uploaded a doc and
    # opted in for this session (Sec 4.5).
    if rag_context:
        messages.append(
            {
                "role": "system",
                "content": f"Relevant excerpts from the document the user uploaded:\n{rag_context}",
            }
        )

    # 6. Current user message.
    messages.append({"role": "user", "content": current_user_message})

    # 7. Tool result — appended later by graph.py's agentic loop, only if
    # a tool call actually happens this turn.
    return messages
