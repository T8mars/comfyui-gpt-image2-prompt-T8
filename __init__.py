"""
ComfyUI GPT Image 2 Prompt - Custom Node Package
Curated GPT Image 2 prompts with thumbnail preview, auto-update, and custom prompt management.
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register API routes for thumbnail serving and prompt management
try:
    from . import api_routes  # noqa: F401
except Exception as e:
    print(f"[GPTImage2Prompt] Warning: API routes not loaded: {e}")

WEB_DIRECTORY = "./web/js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
