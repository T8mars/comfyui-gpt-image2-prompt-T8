"""
ComfyUI GPT Image 2 Prompt - Custom Node Package
Curated GPT Image 2 prompts with thumbnail preview, auto-update, and custom prompt management.
"""

import os
import subprocess
import sys
import threading

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register API routes for thumbnail serving and prompt management
try:
    from . import api_routes  # noqa: F401
except Exception as e:
    print(f"[GPTImage2Prompt] Warning: API routes not loaded: {e}")

WEB_DIRECTORY = "./web/js"

# Auto-build data on first install (when local_prompts.json is missing)
_NODE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_PROMPTS = os.path.join(_NODE_DIR, "data", "local_prompts.json")
if not os.path.isfile(_LOCAL_PROMPTS):
    def _first_run_build():
        build_script = os.path.join(_NODE_DIR, "build_local_prompts.py")
        if not os.path.isfile(build_script):
            return
        print("[GPTImage2Prompt] First run detected - building local prompt data...")
        try:
            result = subprocess.run(
                [sys.executable, build_script],
                capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[-5:]
                print("[GPTImage2Prompt] Build complete:")
                for line in lines:
                    print(f"  {line}")
            else:
                print(f"[GPTImage2Prompt] Build failed: {result.stderr.strip()[:300]}")
        except Exception as e:
            print(f"[GPTImage2Prompt] Build error: {e}")
    # Run in background thread to not block ComfyUI startup
    threading.Thread(target=_first_run_build, daemon=True).start()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
