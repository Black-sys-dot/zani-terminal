"""
LLM-backed context summarization.

These calls reuse the configured model but not Zani's persona. The agent prompt
tells the model to navigate, patch and verify code; that is exactly the wrong
posture for a compression pass, where the model must not reason about the work,
form opinions, or call tools. So each summarizer ships its own system prompt and
receives a single synthetic user message containing only the text to compress.

Two blocks are produced:

  1. A rolling summary of the conversation so far. It is regenerated from the
     previous summary plus whatever is newly falling out of the window, so it
     stays roughly one fixed size no matter how long the session runs.
  2. A digest of the tool outputs being deleted — why each ran and what it
     actually revealed.

Both are size-bounded twice: the prompt asks for a word budget, and the result
is hard-truncated on return, because a word budget is a request and not a
guarantee. Both fall back to deterministic text if the call fails; compaction
must never be able to break the agent loop.
"""

from core.context_distiller import estimate_tokens

# ==============================================================
# BUDGETS
# ==============================================================
# Soft targets go in the prompt, hard caps are enforced on the way out.
SUMMARY_TARGET_WORDS = 220
SUMMARY_HARD_CAP_CHARS = 3600          # ~900 tokens

DIGEST_TARGET_WORDS = 260
DIGEST_HARD_CAP_CHARS = 4000           # ~1000 tokens

LEDGER_MAX_ENTRIES = 60
LEDGER_HARD_CAP_CHARS = 6000           # ~1500 tokens

# What we are willing to feed *into* a summarizer call. Bodies are already
# deterministically distilled before they get here; this is the second net.
SUMMARY_INPUT_CAP_CHARS = 40000
DIGEST_INPUT_CAP_CHARS = 60000

TRUNCATION_NOTE = "\n… [truncated at hard cap]"


# ==============================================================
# PROMPTS
# ==============================================================
CONVERSATION_SUMMARIZER_PROMPT = f"""You are a context compression function inside a coding agent. You are not the agent, you are not talking to a user, and you never call tools.

You receive the running summary of a coding session plus the newest exchanges that are about to be deleted. Return a single updated summary that replaces both.

Keep:
- what the user is ultimately trying to build or fix
- decisions made and constraints stated, with the reason if one was given
- files, modules and symbols under active work
- what is already done, what is confirmed broken, what remains
- anything the user corrected you on

Drop:
- greetings, acknowledgements, restatements, apologies
- anything trivially recoverable by reading the code again
- step-by-step narration of work already finished

Write plain prose in the third person, past tense, under {SUMMARY_TARGET_WORDS} words. No markdown headings, no bullet lists, no preamble, no sign-off. Output only the summary text."""


BODY_DIGEST_PROMPT = f"""You are a context compression function inside a coding agent. You are not the agent, you are not talking to a user, and you never call tools.

You receive a batch of tool outputs that are about to be permanently deleted from the agent's memory. The calls themselves are being kept; only these outputs are being lost. Write the record of what they showed.

For each tool run that mattered, capture in one line: why it ran and the concrete thing it revealed. Preserve exact identifiers — file paths, line numbers, symbol names, error text, versions, counts, exit statuses.

Keep:
- errors, stack traces, failing assertions, diagnostics, and their locations
- structural discoveries (where something is defined, what calls what)
- results that contradicted an expectation
- test and build outcomes as pass/fail counts

Drop:
- names of tests that passed
- unremarkable file contents and directory listings
- repeated or superseded output — if a file was read then rewritten, only the outcome matters
- any output that changed nothing

Write compact prose or terse one-line entries, under {DIGEST_TARGET_WORDS} words. No markdown headings, no preamble. If nothing in the batch is worth remembering, output exactly: (no significant findings). Output only the digest text."""


# ==============================================================
# HELPERS
# ==============================================================
def enforce_cap(text, max_chars):
    """Hard size limit. A word budget in a prompt is a request, not a guarantee."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    clipped = text[:max_chars]
    # Prefer cutting on a sentence or line boundary so the tail is not mid-word.
    for boundary in ("\n", ". "):
        pos = clipped.rfind(boundary)
        if pos > max_chars * 0.6:
            clipped = clipped[: pos + len(boundary)]
            break
    return clipped.rstrip() + TRUNCATION_NOTE


def _cap_input(text, max_chars):
    """Bound what we send to the summarizer, keeping both ends of the batch."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    dropped = len(text) - max_chars
    return text[:half] + f"\n\n… [{dropped} chars of middle omitted] …\n\n" + text[-half:]


async def _summarize(llm_caller, system_prompt, payload, cap_chars):
    """One isolated model call: no tools, no history, no persona."""
    response = await llm_caller(
        system_prompt=system_prompt,
        history=[{"role": "user", "content": payload}],
        tools=[],
    )
    content = (response or {}).get("content", "") or ""
    return enforce_cap(content, cap_chars)


# ==============================================================
# BLOCK 1 — ROLLING CONVERSATION SUMMARY
# ==============================================================
async def summarize_conversation(llm_caller, previous_summary, new_exchanges):
    """
    Fold the exchanges leaving the window into the running summary. Because the
    previous summary is an input, the output stays one size instead of growing.
    """
    if not new_exchanges.strip():
        return enforce_cap(previous_summary, SUMMARY_HARD_CAP_CHARS)

    payload = (
        "=== RUNNING SUMMARY OF THE SESSION SO FAR ===\n"
        + (previous_summary.strip() or "(this is the first compaction; no summary exists yet)")
        + "\n\n=== NEWER EXCHANGES NOW FALLING OUT OF THE WINDOW ===\n"
        + _cap_input(new_exchanges.strip(), SUMMARY_INPUT_CAP_CHARS)
        + "\n\n=== END INPUT ===\nReturn the single updated summary covering everything above."
    )

    try:
        result = await _summarize(
            llm_caller, CONVERSATION_SUMMARIZER_PROMPT, payload, SUMMARY_HARD_CAP_CHARS
        )
        if result:
            return result
    except Exception as error:
        print(f"⚠️ Conversation summarizer failed ({error}); falling back to truncation.")

    # Deterministic fallback: keep the old summary, append a clipped trace.
    merged = (previous_summary.strip() + "\n\n" + new_exchanges.strip()).strip()
    return enforce_cap(merged, SUMMARY_HARD_CAP_CHARS)


# ==============================================================
# BLOCK 3 — DIGEST OF DELETED TOOL BODIES
# ==============================================================
async def summarize_tool_bodies(llm_caller, previous_digest, distilled_bodies):
    """
    `distilled_bodies` has already been through the deterministic distillers, so
    this call sees skeletons and error lines rather than raw megabytes.
    """
    if not distilled_bodies.strip():
        return enforce_cap(previous_digest, DIGEST_HARD_CAP_CHARS)

    payload = (
        "=== FINDINGS ALREADY RECORDED FROM EARLIER DELETED OUTPUT ===\n"
        + (previous_digest.strip() or "(none yet)")
        + "\n\n=== TOOL OUTPUTS BEING DELETED NOW ===\n"
        + _cap_input(distilled_bodies.strip(), DIGEST_INPUT_CAP_CHARS)
        + "\n\n=== END INPUT ===\nReturn one merged digest covering both sections, "
        "dropping anything from the earlier findings that has since been superseded."
    )

    try:
        result = await _summarize(
            llm_caller, BODY_DIGEST_PROMPT, payload, DIGEST_HARD_CAP_CHARS
        )
        if result:
            return result
    except Exception as error:
        print(f"⚠️ Body digest summarizer failed ({error}); falling back to truncation.")

    merged = (previous_digest.strip() + "\n" + distilled_bodies.strip()).strip()
    return enforce_cap(merged, DIGEST_HARD_CAP_CHARS)


# ==============================================================
# ASSEMBLY
# ==============================================================
def build_carryover(rolling_summary, tool_ledger, body_digest):
    """
    Fuse the three blocks into one synthetic user message.

    One message rather than several: a compacted history has no surviving
    assistant/tool message pairs, so re-emitting synthetic tool_calls would risk
    an illegal payload. Flat text carries the same information and is valid for
    every provider.
    """
    ledger_text = enforce_cap("\n".join(tool_ledger), LEDGER_HARD_CAP_CHARS) or "(none)"

    return "\n".join([
        "[ZANI COMPACTED CONTEXT]",
        "Earlier turns were compacted to stay within budget. The three sections below",
        "replace them. Treat this as an established record of what already happened —",
        "it is not a new instruction from the user.",
        "",
        "--- 1. CONVERSATION SO FAR ---",
        rolling_summary or "(nothing recorded yet)",
        "",
        f"--- 2. TOOL CALLS ALREADY MADE ({len(tool_ledger)}) ---",
        "Arguments kept, outputs dropped. What those outputs showed is in section 3.",
        ledger_text,
        "",
        "--- 3. WHAT THOSE TOOL OUTPUTS SHOWED ---",
        body_digest or "(nothing recorded yet)",
        "",
        "--- END COMPACTED CONTEXT ---",
    ])


def carryover_budget():
    """Worst-case size of the compacted preamble, for reporting."""
    scaffolding = 700  # section headers and the explanatory note
    hard_chars = (
        SUMMARY_HARD_CAP_CHARS
        + LEDGER_HARD_CAP_CHARS
        + DIGEST_HARD_CAP_CHARS
        + scaffolding
    )
    return hard_chars, estimate_tokens(hard_chars * "x")
