"""
Implements the rolling block scheme in Technical PRD Sec 4.3.

Rules (confirmed logic from the PRD table):
- The two most recent messages always stay raw.
- Once a new block of 7 messages accumulates, everything in it except the
  last 2 is collapsed into one summary.
- Only the very first block additionally preserves its first 2 messages
  raw (the conversation's opening). Later blocks don't get this treatment.
- Each block is frozen once created — never re-summarized later.
- Session locks at 20 messages (a third block never forms: 21 > the cap).

This module is pure/stateless with respect to *how* a block gets
summarized (that's an LLM call, done once when a block first freezes and
cached) — it only computes block boundaries and assembles final context.
"""

from __future__ import annotations

from dataclasses import dataclass

BLOCK_SIZE = 7
SESSION_MESSAGE_CAP = 20


@dataclass
class Block:
    index: int  # 0 = first block ("Block A"), 1 = second ("Block B"), ...
    start: int  # 1-indexed message position, inclusive
    end: int  # 1-indexed message position, inclusive
    raw_head: tuple[int, int] | None  # only set for the first block
    raw_tail: tuple[int, int]
    summarized_range: tuple[int, int]


def frozen_blocks(total_messages: int) -> list[Block]:
    """Returns every block that is fully frozen given the current message
    count. A block freezes only once its 7th message has arrived."""
    blocks: list[Block] = []
    n_complete_blocks = total_messages // BLOCK_SIZE
    for i in range(n_complete_blocks):
        start = i * BLOCK_SIZE + 1
        end = start + BLOCK_SIZE - 1
        if i == 0:
            blocks.append(
                Block(
                    index=i,
                    start=start,
                    end=end,
                    raw_head=(start, start + 1),
                    raw_tail=(end - 1, end),
                    summarized_range=(start + 2, end - 2),
                )
            )
        else:
            blocks.append(
                Block(
                    index=i,
                    start=start,
                    end=end,
                    raw_head=None,
                    raw_tail=(end - 1, end),
                    summarized_range=(start, end - 2),
                )
            )
    return blocks


def is_session_locked(total_messages: int) -> bool:
    return total_messages >= SESSION_MESSAGE_CAP


def newly_frozen_block(
    total_messages_before: int, total_messages_after: int
) -> Block | None:
    """Called after appending a message — returns the block that just
    became frozen this turn, if any, so its summary can be generated once
    and cached (never re-summarized later, per the PRD)."""
    before = frozen_blocks(total_messages_before)
    after = frozen_blocks(total_messages_after)
    if len(after) > len(before):
        return after[-1]
    return None


def build_context_messages(
    messages: list[dict],
    block_summaries: dict[int, str],
) -> list[dict]:
    """Assembles the final message list for the LLM context (item 4 of
    Sec 4.2's ordering): frozen blocks render as one summary message each
    (except their raw head/tail), and anything past the last frozen block
    (msgs 15-19 in the example) stays fully raw."""
    total = len(messages)
    blocks = frozen_blocks(total)
    result: list[dict] = []
    covered_through = 0

    for block in blocks:
        if block.raw_head:
            h0, h1 = block.raw_head
            result.extend(messages[h0 - 1 : h1])
        s0, s1 = block.summarized_range
        summary_text = block_summaries.get(block.index, "[summary pending]")
        result.append(
            {
                "role": "system",
                "content": f"[Earlier in this conversation: {summary_text}]",
            }
        )
        t0, t1 = block.raw_tail
        result.extend(messages[t0 - 1 : t1])
        covered_through = block.end

    # Anything after the last frozen block stays raw (msgs 15-19 case).
    result.extend(messages[covered_through:])
    return result
