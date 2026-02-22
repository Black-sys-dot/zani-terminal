# ==============================================================
# FILE: core/zani_brain.py
# ==============================================================

from google import genai
from google.genai import types


# --------------------------------------------------------------
# SYSTEM IDENTITY
# --------------------------------------------------------------
SYSTEM_IDENTITY = (
    "You are Zani, a coding agent.\n"
    "Follow history for latest file versions.\n"
    "Use tools when file operations are required."
)


# --------------------------------------------------------------
# TOOL SCHEMA BUILDERS (MODEL-FACING ONLY)
# --------------------------------------------------------------
# IMPORTANT:
# These are NOT python functions.
# These are Gemini tool definitions (schemas).
# The real python execution happens in zani.py via AVAILABLE_TOOLS.
# --------------------------------------------------------------

def build_write_file_tool_schema():
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="write_to_file",
                description="Write content to a file",
                parameters={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "File path to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write into file"
                        }
                    },
                    "required": ["filename", "content"]
                }
            )
        ]
    )


# --------------------------------------------------------------
# ZANI BRAIN
# --------------------------------------------------------------

class ZaniBrain:

    def __init__(self, api_key, model_name="gemini-3-flash-preview"):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

        # TOOL SCHEMAS ONLY (NOT PYTHON FUNCTIONS)
        self.tools = [
            build_write_file_tool_schema()
        ]

        # Base config (used when NO explicit cache)
        self.base_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_IDENTITY,
            tools=self.tools
        )


    # ----------------------------------------------------------
    # START CHAT SESSION
    # ----------------------------------------------------------
    def start_session(self, history, cache_name=None):

        # When explicit cache is used,
        # DO NOT send system_instruction or tools again.
        # They already exist inside cached content.
        if cache_name:
            config = types.GenerateContentConfig(
                cached_content=cache_name
            )
        else:
            config = self.base_config

        return self.client.chats.create(
            model=self.model_name,
            history=history,
            config=config
        )


    # ----------------------------------------------------------
    # CREATE EXPLICIT CACHE
    # ----------------------------------------------------------
    def create_explicit_cache(self, context_text, ttl_hours):

        cache = self.client.caches.create(
            model=self.model_name,
            config=types.CreateCachedContentConfig(
                system_instruction=SYSTEM_IDENTITY,
                tools=self.tools,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=context_text)]
                    )
                ],
                ttl=f"{ttl_hours * 3600}s"
            )
        )

        return cache


    # ----------------------------------------------------------
    # TERMINATE CACHE
    # ----------------------------------------------------------
    def terminate_cache(self, cache_name):
        try:
            self.client.caches.delete(name=cache_name)
            return True
        except Exception:
            return False
