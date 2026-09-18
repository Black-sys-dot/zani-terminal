"""
Payload distillation for long agent sessions.

Old messages are rewritten, not deleted. Every message keeps its position, its
role, and its tool_call_id pairing, so a distilled history stays a legal payload
for both the OpenAI-style and the Google function-calling APIs. Only the noisy
interior of a payload is thrown away: file bodies collapse to a structural
skeleton, search hits to a line index, shell logs to head/tail plus the error
lines, JSON to its shape, and written file contents to a byte count.

Every distiller returns None when it does not recognise the payload, so the
dispatcher can fall through to the next strategy.
"""

import json
import re

CHARS_PER_TOKEN = 4

# Below this a payload is already cheap, and distilling it costs more in
# explanatory header than it saves.
MIN_DISTILL_CHARS = 400

# Marks content we have already rewritten, so a second compaction pass leaves
# it alone instead of distilling a distillation.
DISTILL_MARKER = "[distilled"

# Keys whose values are bulk write payloads rather than instructions. Once the
# write has happened the body is dead weight; the path is the information.
BULK_ARG_KEYS = {"content", "text", "body", "data", "patch", "source", "new_text", "code"}

_ERROR_PATTERN = re.compile(
    r"(error|exception|traceback|fail|fatal|panic|assert|undefined|not found|"
    r"cannot|refused|denied|timeout|warning)",
    re.IGNORECASE,
)

# Declaration lines worth keeping when a code file is reduced to a skeleton.
_SKELETON_PATTERN = re.compile(
    r"^\s*(def |class |async def |func |fn |function |type |struct |impl |trait |"
    r"interface |import |from |package |const |export |module\.exports|#include|"
    r"@app\.|@router\.)"
)

# `path:line: source text` — the shape emitted by zani_global_search and by
# most LSP reference listings.
_LOCATION_PATTERN = re.compile(r"^(.+?):(\d+):\s?(.*)$")


def estimate_tokens(text: str) -> int:
    # Rough heuristic: 1 token ~ 4 characters.
    return len(text) // CHARS_PER_TOKEN


# ==============================================================
# JSON
# ==============================================================
def _json_skeleton(node, depth=0, max_depth=4):
    """Collapse a parsed payload to its shape: keys and types survive, bulk values do not."""
    if depth >= max_depth:
        return "..."

    if isinstance(node, dict):
        out = {}
        for i, (key, value) in enumerate(node.items()):
            if i >= 25:
                out[f"...+{len(node) - 25} more keys"] = ""
                break
            out[key] = _json_skeleton(value, depth + 1, max_depth)
        return out

    if isinstance(node, list):
        if not node:
            return []
        head = _json_skeleton(node[0], depth + 1, max_depth)
        if len(node) == 1:
            return [head]
        return [head, f"...+{len(node) - 1} more items"]

    if isinstance(node, str) and len(node) > 80:
        return node[:80] + f"...(+{len(node) - 80} chars)"

    return node


def distill_json(text):
    """LSP servers and many MCP tools answer in JSON. Keep the shape, drop the bulk."""
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return None

    skeleton = json.dumps(_json_skeleton(parsed), indent=1, default=str)
    return f"{DISTILL_MARKER} json — shape kept, bulk values dropped]\n{skeleton}"


# ==============================================================
# SEARCH / REFERENCE LISTINGS
# ==============================================================
def distill_locations(text):
    """`path:line: source` triples. The locations are the information; the quoted source is the bulk."""
    per_file = {}
    trailing = []

    for line in text.splitlines():
        match = _LOCATION_PATTERN.match(line)
        if match:
            per_file.setdefault(match.group(1), []).append(match.group(2))
        elif line.strip():
            trailing.append(line.strip())

    if not per_file:
        return None

    total = sum(len(lines) for lines in per_file.values())
    out = [
        f"{DISTILL_MARKER} search — {total} matches across {len(per_file)} files, "
        "match text dropped, locations kept]"
    ]

    for path, lines in list(per_file.items())[:40]:
        shown = ",".join(lines[:12])
        more = f" +{len(lines) - 12} more" if len(lines) > 12 else ""
        out.append(f"{path}: lines {shown}{more}")

    if len(per_file) > 40:
        out.append(f"...+{len(per_file) - 40} more files")

    out.extend(trailing[:2])
    return "\n".join(out)


# ==============================================================
# FILE DUMPS
# ==============================================================
def distill_file_dump(text):
    lines = text.splitlines()
    header = (
        f"{DISTILL_MARKER} file — {len(lines)} lines, {len(text)} chars; "
        "body dropped, structure kept]"
    )

    skeleton = [
        f"{i}: {line.rstrip()}"
        for i, line in enumerate(lines, 1)
        if _SKELETON_PATTERN.match(line)
    ]

    if not skeleton:
        # Prose, config or data rather than code: head and tail carry the most.
        if len(lines) <= 24:
            return None
        kept = lines[:12] + [f"... {len(lines) - 24} lines omitted ..."] + lines[-12:]
        return "\n".join([header] + kept)

    if len(skeleton) > 60:
        skeleton = skeleton[:60] + [f"...+{len(skeleton) - 60} more declarations"]

    return "\n".join([header] + skeleton)


# ==============================================================
# SHELL / LOG OUTPUT
# ==============================================================
def distill_shell_output(text):
    """Keep the head, the tail, and whatever looked like a diagnostic in between."""
    lines = text.splitlines()
    if len(lines) <= 30:
        return None

    head, tail, middle = lines[:8], lines[-12:], lines[8:-12]
    salient = [line for line in middle if _ERROR_PATTERN.search(line)][:20]

    out = [
        f"{DISTILL_MARKER} shell output — {len(lines)} lines; head, tail and "
        f"{len(salient)} diagnostic lines kept]"
    ]
    out.extend(head)
    if salient:
        out.append(f"... {len(middle)} middle lines omitted, salient ones follow ...")
        out.extend(salient)
    else:
        out.append(f"... {len(middle)} middle lines omitted ...")
    out.extend(tail)

    return "\n".join(out)


# ==============================================================
# DIRECTORY LISTINGS
# ==============================================================
def distill_directory(text):
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 25:
        return None

    dirs = [line for line in lines if line.startswith("[DIR]")]
    files = [line for line in lines if line.startswith("[FILE]")]
    if not dirs and not files:
        return None

    out = [f"{DISTILL_MARKER} listing — {len(dirs)} dirs, {len(files)} files]"]
    out.extend(dirs[:15])
    if len(dirs) > 15:
        out.append(f"...+{len(dirs) - 15} more dirs")
    out.extend(files[:15])
    if len(files) > 15:
        out.append(f"...+{len(files) - 15} more files")

    return "\n".join(out)


# ==============================================================
# DISPATCH
# ==============================================================
_FILE_TOOLS = {"read_file"}
_LOCATION_TOOLS = {"zani_global_search", "search_files", "references", "definition"}
_SHELL_TOOLS = {"run_bash_command"}
_DIR_TOOLS = {"list_directory"}


def distill_tool_result(tool_name, content):
    """Reduce one tool result. Returns content unchanged when nothing applies."""
    if not content or len(content) < MIN_DISTILL_CHARS:
        return content
    if content.lstrip().startswith(DISTILL_MARKER):
        return content

    name = (tool_name or "").lower()

    if name in _LOCATION_TOOLS:
        distilled = distill_locations(content)
    elif name in _FILE_TOOLS:
        distilled = distill_file_dump(content)
    elif name in _SHELL_TOOLS:
        distilled = distill_shell_output(content)
    elif name in _DIR_TOOLS:
        distilled = distill_directory(content)
    else:
        distilled = None

    # Fall through by shape for anything unrecognised — LSP tool names vary by
    # language server, so we sniff the payload rather than trusting the name.
    if distilled is None:
        distilled = distill_json(content)
    if distilled is None:
        distilled = distill_locations(content)
    if distilled is None:
        distilled = distill_shell_output(content)
    if distilled is None:
        distilled = (
            f"{DISTILL_MARKER} payload — first 1200 of {len(content)} chars kept]\n"
            + content[:1200]
        )

    # Never let distillation make a payload larger than it was.
    return distilled if len(distilled) < len(content) else content


def distill_tool_arguments(arguments):
    """
    Trim bulk out of a recorded tool call. write_file carries an entire file
    body in its arguments, which is the single largest sink in a long session.
    """
    was_string = isinstance(arguments, str)

    if was_string:
        try:
            parsed = json.loads(arguments)
        except (ValueError, TypeError):
            if len(arguments) < MIN_DISTILL_CHARS:
                return arguments
            return arguments[:200] + f"... [+{len(arguments) - 200} chars dropped]"
    else:
        parsed = arguments

    if not isinstance(parsed, dict):
        return arguments

    trimmed = {}
    changed = False

    for key, value in parsed.items():
        if not isinstance(value, str):
            trimmed[key] = value
        elif key.lower() in BULK_ARG_KEYS and len(value) > 200:
            trimmed[key] = f"<{len(value)} chars written, body dropped from history>"
            changed = True
        elif len(value) > 600:
            trimmed[key] = value[:200] + f"... [+{len(value) - 200} chars dropped]"
            changed = True
        else:
            trimmed[key] = value

    if not changed:
        return arguments

    return json.dumps(trimmed) if was_string else trimmed
