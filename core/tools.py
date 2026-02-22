import os

def write_to_file(filename: str, content: str) -> str:
    """
    Creates or overwrites a file with the provided content.
    Returns a success or error message.
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Successfully wrote to {filename}"
    except Exception as e:
        return f"❌ Failed to write {filename}: {str(e)}"

# A dictionary mapping tool names to their actual functions for the dispatcher
AVAILABLE_TOOLS = {
    "write_to_file": write_to_file
}