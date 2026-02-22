import json
import os
import hashlib

GENESIS_MARKER = "--- INITIAL CODEBASE SNAPSHOT ---"
FILE_UPDATE_PREFIX = "SYSTEM FILE UPDATE:"
SUMMARY_PREFIX = "Conversation summary:"


class MemoryManager:
    def __init__(self, history_file=".zani/history.json"):
        self.history_file = history_file

    # ----------------------------------------------------------
    # LOAD
    # ----------------------------------------------------------

    def load_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    # ----------------------------------------------------------
    # SAVE TURN
    # ----------------------------------------------------------

    def save_turn(self, role, text):
        history = self.load_history()
        history.append({
            "role": role,
            "parts": [{"text": text}]
        })
        self._write(history)

    # ----------------------------------------------------------
    # GENESIS
    # ----------------------------------------------------------

    def save_genesis_block(self, project_context):
        history = self.load_history()

        if not history:
            history.insert(0, {
                "role": "user",
                "parts": [{"text": project_context}]
            })
            self._write(history)
            return

        first = history[0]["parts"][0].get("text", "")
        if GENESIS_MARKER not in first:
            history.insert(0, {
                "role": "user",
                "parts": [{"text": project_context}]
            })
            self._write(history)

    # ----------------------------------------------------------
    # FILE UPDATE LOG
    # ----------------------------------------------------------

    def save_file_update(self, filename, content):
        digest = hashlib.sha256(content.encode()).hexdigest()[:12]
        log = f"{FILE_UPDATE_PREFIX} {filename} | sha256={digest}"
        self.save_turn("user", log)

    # ----------------------------------------------------------
    # HELPERS FOR SUMMARIZATION FILTERING
    # ----------------------------------------------------------

    def is_file_update(self, text):
        return text.startswith(FILE_UPDATE_PREFIX)

    def is_summary(self, text):
        return text.startswith(SUMMARY_PREFIX)

    # ----------------------------------------------------------
    # CLEAR
    # ----------------------------------------------------------

    def clear_history(self):
        if os.path.exists(self.history_file):
            os.remove(self.history_file)

    # ----------------------------------------------------------
    # WRITE
    # ----------------------------------------------------------

    def _write(self, history):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
