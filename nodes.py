"""
ComfyUI GPT Image 2 Prompt Nodes
Based on: https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts
All thumbnails are served from local files - no online URL fetching.
"""

import os
import json
import time
import hashlib
import shutil
import urllib.request
import urllib.error
import threading
from datetime import datetime
from pathlib import Path

import folder_paths

# ============================================================
# Paths  (all resolved within NODE_DIR - fully self-contained)
# ============================================================
NODE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(NODE_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")        # Local images copied from repo
IMAGE_BASE = DATA_DIR                                # Base dir for resolving image_path in JSON

LOCAL_PROMPTS_JSON = os.path.join(DATA_DIR, "local_prompts.json")
CUSTOM_PROMPTS_DIR = os.path.join(DATA_DIR, "custom_prompts")
CUSTOM_PROMPTS_JSON = os.path.join(CUSTOM_PROMPTS_DIR, "custom_prompts.json")
UPDATE_STATE_FILE = os.path.join(DATA_DIR, "update_state.json")

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/EvoLinkAI/awesome-gpt-image-2-prompts/main"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CUSTOM_PROMPTS_DIR, exist_ok=True)


# ============================================================
# Utility helpers
# ============================================================
def _load_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _url_to_filename(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest() + ".jpg"


def _download_file(url: str, dest: str, timeout: int = 30) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-GPTImage2Prompt/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        return True
    except Exception as e:
        print(f"[GPTImage2Prompt] Download failed {url}: {e}")
        return False


def _load_all_prompts():
    """Load local prompts (from parsed README) and custom prompts."""
    presets = _load_json(LOCAL_PROMPTS_JSON, [])
    customs = _load_json(CUSTOM_PROMPTS_JSON, [])
    return presets, customs


def _get_prompt_image_path(prompt_data: dict) -> str:
    """Get the absolute path to a prompt's local image file.
    All images are stored within NODE_DIR/data/.
    Supports both 'image_path' (relative to DATA_DIR) and legacy 'thumbnail' (absolute) fields.
    """
    image_rel = prompt_data.get("image_path", "")
    if image_rel:
        # Resolve relative to IMAGE_BASE (= DATA_DIR)
        image_rel_os = image_rel.replace("/", os.sep)
        abs_path = os.path.join(IMAGE_BASE, image_rel_os)
        if os.path.exists(abs_path):
            return abs_path
    # Fallback: legacy 'thumbnail' field (absolute path)
    thumb = prompt_data.get("thumbnail", "")
    if thumb and os.path.exists(thumb):
        return thumb
    return ""


def _get_prompt_choices():
    """Build prompt choice list with category and title."""
    presets, customs = _load_all_prompts()
    choices = []
    for i, p in enumerate(presets):
        cat = p.get("category", "")
        title = p.get("title", "")
        author = p.get("author", "")
        text_preview = p.get("text", "")[:60].replace("\n", " ")
        label = f"[{cat}] {title}"
        if author:
            label += f" (@{author})"
        if not title:
            label = f"[{cat}] {text_preview}"
        choices.append(f"[preset_{i}] {label}")
    for i, p in enumerate(customs):
        name = p.get("name", p.get("text", "")[:50])
        choices.append(f"[custom_{i}] {name}")
    if not choices:
        choices = ["No prompts available - run build_local_prompts.py first"]
    return choices


def _get_categories():
    """Available categories - dynamically built from data."""
    base = ["all"]
    presets = _load_json(LOCAL_PROMPTS_JSON, [])
    cats_in_data = sorted(set(p.get("category", "other") for p in presets))
    base.extend(cats_in_data)
    base.append("custom")
    # Deduplicate while preserving order
    seen = set()
    result = []
    for c in base:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result if len(result) > 2 else ["all", "portrait", "poster", "character", "ui", "comparison", "custom"]


# ============================================================
# Helper: parse selection string to get prompt data
# ============================================================
def _parse_selection(prompt_selection: str):
    """Parse '[preset_N]...' or '[custom_N]...' string. Returns (prompt_data, prompt_text, image_path)."""
    presets, customs = _load_all_prompts()
    prompt_data = None
    prompt_text = ""
    image_path = ""

    if prompt_selection.startswith("[preset_"):
        idx_str = prompt_selection.split("]")[0].replace("[preset_", "")
        try:
            idx = int(idx_str)
            if 0 <= idx < len(presets):
                prompt_data = presets[idx]
                prompt_text = prompt_data.get("text", "")
                image_path = _get_prompt_image_path(prompt_data)
        except (ValueError, IndexError):
            pass
    elif prompt_selection.startswith("[custom_"):
        idx_str = prompt_selection.split("]")[0].replace("[custom_", "")
        try:
            idx = int(idx_str)
            if 0 <= idx < len(customs):
                prompt_data = customs[idx]
                prompt_text = prompt_data.get("text", "")
                image_path = _get_prompt_image_path(prompt_data)
        except (ValueError, IndexError):
            pass

    return prompt_data, prompt_text, image_path


# ============================================================
# Node: GPT Image 2 Prompt Selector
# ============================================================
class GPTImage2PromptSelector:
    """Select a GPT Image 2 prompt with local thumbnail preview and editable prompt box.
    The selected prompt is filled into the editable text box for user modification.
    Preview thumbnail is served from local cache (not online URL).
    Final output is the edited prompt STRING."""

    CATEGORY = "GPT Image 2 Prompts"
    FUNCTION = "select_prompt"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    OUTPUT_NODE = True  # Needed to send UI data (thumbnail) back to frontend

    @classmethod
    def INPUT_TYPES(cls):
        choices = _get_prompt_choices()
        categories = _get_categories()
        return {
            "required": {
                "category": (categories, {"default": "all"}),
                "prompt_selection": (choices, {"default": choices[0]}),
                "edit_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Select a prompt above, it will be filled here for editing. Your edits become the final output.",
                    "dynamicPrompts": False,
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Always re-execute so UI thumbnail updates
        return float("nan")

    def select_prompt(self, category, prompt_selection, edit_prompt=""):
        prompt_data, original_text, image_path = _parse_selection(prompt_selection)

        # If user has edited the prompt, use the edited version; otherwise use original
        final_prompt = edit_prompt.strip() if edit_prompt.strip() else original_text

        # Build image_path for frontend (relative path within repo for API serving)
        image_rel = prompt_data.get("image_path", "") if prompt_data else ""

        return {
            "ui": {
                "image_path": [image_rel],  # e.g. "images/portrait_case1/output.jpg"
                "original_prompt": [original_text],
            },
            "result": (final_prompt,),
        }


# ============================================================
# Node: GPT Image 2 Prompt Updater
# ============================================================
class GPTImage2PromptUpdater:
    """Update prompts by downloading latest data from GitHub and opennana.com."""

    CATEGORY = "GPT Image 2 Prompts"
    FUNCTION = "update_prompts"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sync_github": ("BOOLEAN", {"default": True, "label_on": "Yes", "label_off": "No"}),
                "sync_opennana": ("BOOLEAN", {"default": True, "label_on": "Yes", "label_off": "No"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def update_prompts(self, sync_github=True, sync_opennana=True, seed=0):
        import subprocess
        import sys

        status_parts = []

        # Record pre-update counts for comparison
        old_presets = _load_json(LOCAL_PROMPTS_JSON, [])
        old_count = len(old_presets)
        old_with_text = sum(1 for p in old_presets if p.get("text", "").strip())

        # Sync from GitHub: download latest README + incremental images
        if sync_github:
            try:
                build_script = os.path.join(NODE_DIR, "build_local_prompts.py")
                result = subprocess.run(
                    [sys.executable, build_script],
                    capture_output=True, text=True, timeout=600
                )
                if result.returncode == 0:
                    # Extract key lines from output
                    lines = result.stdout.strip().split("\n")
                    summary_lines = [l for l in lines if "total" in l.lower() or "stage" in l.lower()
                                     or "download" in l.lower() or "copied" in l.lower()
                                     or "===" in l]
                    output = "\n".join(summary_lines[-10:]) if summary_lines else result.stdout.strip()[-500:]
                    status_parts.append(f"GitHub sync: {output}")
                else:
                    status_parts.append(f"GitHub sync failed: {result.stderr.strip()[:500]}")
            except Exception as e:
                status_parts.append(f"GitHub sync error: {e}")

        # Sync from opennana.com (incremental, after rebuild)
        if sync_opennana:
            try:
                from fetch_opennana import sync_from_opennana
                opennana_result = sync_from_opennana(targets=None, dry_run=False, delay=1.0)
                status_parts.append(opennana_result["message"])
            except ImportError:
                # Try relative import path
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        "fetch_opennana",
                        os.path.join(NODE_DIR, "fetch_opennana.py")
                    )
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    opennana_result = mod.sync_from_opennana(targets=None, dry_run=False, delay=1.0)
                    status_parts.append(opennana_result["message"])
                except Exception as e:
                    status_parts.append(f"OpenNana sync error: {e}")
            except Exception as e:
                status_parts.append(f"OpenNana sync error: {e}")

        # Count new results and compare
        presets = _load_json(LOCAL_PROMPTS_JSON, [])
        customs = _load_json(CUSTOM_PROMPTS_JSON, [])
        new_count = len(presets)
        new_with_text = sum(1 for p in presets if p.get("text", "").strip())

        # Check images
        with_images = sum(1 for p in presets if _get_prompt_image_path(p))

        status_parts.append(f"Total: {new_count} presets ({new_with_text} with prompt text), {len(customs)} custom.")
        status_parts.append(f"Presets with local images: {with_images}/{new_count}")

        # Show delta
        if old_count > 0:
            delta = new_count - old_count
            text_delta = new_with_text - old_with_text
            if delta != 0 or text_delta != 0:
                status_parts.append(f"Changes: {delta:+d} presets, {text_delta:+d} with text")
            else:
                status_parts.append("No changes detected (already up to date).")

        _save_json(UPDATE_STATE_FILE, {
            "last_update": time.time(),
            "last_update_time": datetime.now().isoformat(),
            "prompt_count": len(presets),
            "with_images": with_images,
        })

        status_str = "\n".join(status_parts)
        return {
            "ui": {
                "status": [status_str],
                "preset_count": [new_count],
                "with_images": [with_images],
            },
            "result": (status_str,),
        }


# ============================================================
# Node: GPT Image 2 Custom Prompt Saver
# ============================================================
class GPTImage2CustomPromptSaver:
    """Manually create and save a prompt with an optional preview image."""

    CATEGORY = "GPT Image 2 Prompts"
    FUNCTION = "save_prompt"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_text": ("STRING", {"default": "", "multiline": True,
                                           "placeholder": "Enter your GPT Image 2 prompt here"}),
                "prompt_name": ("STRING", {"default": "", "placeholder": "Short name / title for this prompt"}),
                "category": (["custom", "portrait", "poster", "character", "ui", "comparison"],
                             {"default": "custom"}),
            },
            "optional": {
                "preview_image": ("IMAGE",),
            },
        }

    def save_prompt(self, prompt_text, prompt_name, category, preview_image=None):
        if not prompt_text.strip():
            return ("Error: prompt text is empty.",)

        customs = _load_json(CUSTOM_PROMPTS_JSON, [])
        effective_name = prompt_name if prompt_name else prompt_text[:50]

        # Check if a custom prompt with the same name already exists
        existing_idx = None
        for idx, c in enumerate(customs):
            if c.get("name", "") == effective_name:
                existing_idx = idx
                break

        if existing_idx is not None:
            # Overwrite: reuse existing id, delete old image if present
            old_entry = customs[existing_idx]
            use_id = old_entry.get("id", f"custom_{int(time.time())}_{existing_idx}")
            old_img = old_entry.get("image_path", "")
            if old_img:
                old_abs = os.path.join(IMAGE_BASE, old_img.replace("/", os.sep))
                if os.path.isfile(old_abs):
                    try:
                        os.remove(old_abs)
                    except Exception:
                        pass
        else:
            use_id = f"custom_{int(time.time())}_{len(customs)}"

        image_rel = ""  # Relative path from DATA_DIR (for API serving)

        # Save preview image if provided
        if preview_image is not None:
            try:
                import numpy as np
                from PIL import Image

                # ComfyUI IMAGE tensor: [B, H, W, C] float 0-1
                img_array = preview_image[0].cpu().numpy()
                img_array = (img_array * 255).clip(0, 255).astype(np.uint8)
                img = Image.fromarray(img_array)

                thumb_filename = f"{use_id}.jpg"
                abs_path = os.path.join(CUSTOM_PROMPTS_DIR, thumb_filename)
                img.save(abs_path, "JPEG", quality=85)
                # Store as relative path from DATA_DIR: "custom_prompts/xxx.jpg"
                image_rel = f"custom_prompts/{thumb_filename}"
            except Exception as e:
                print(f"[GPTImage2Prompt] Failed to save preview: {e}")

        entry = {
            "id": use_id,
            "text": prompt_text,
            "name": effective_name,
            "category": category,
            "createdAt": datetime.now().isoformat(),
            "image_path": image_rel,  # Relative to DATA_DIR, same format as presets
            "image_exists": bool(image_rel),
        }

        if existing_idx is not None:
            customs[existing_idx] = entry
            action = "Updated"
        else:
            customs.append(entry)
            action = "Saved"
        _save_json(CUSTOM_PROMPTS_JSON, customs)

        status_msg = f"{action} prompt '{effective_name}' (id: {use_id}). Total custom: {len(customs)}"
        return {
            "ui": {
                "status": [status_msg],
                "saved_id": [use_id],
            },
            "result": (status_msg,),
        }


# ============================================================
# Node: GPT Image 2 Execution Checker
# ============================================================
class GPTImage2ExecutionChecker:
    """Verify ComfyUI is executing correctly. Passes through any input and reports status."""

    CATEGORY = "GPT Image 2 Prompts"
    FUNCTION = "check_execution"
    RETURN_TYPES = ("STRING", "BOOLEAN",)
    RETURN_NAMES = ("status_report", "is_healthy",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "check_data_files": ("BOOLEAN", {"default": True}),
                "check_network": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "passthrough_string": ("STRING", {"default": "", "forceInput": True}),
            },
        }

    def check_execution(self, check_data_files, check_network, passthrough_string=""):
        report_lines = []
        healthy = True

        # 1. Basic execution check
        report_lines.append("[OK] ComfyUI node execution is working.")

        # 2. Check data files
        if check_data_files:
            if os.path.exists(LOCAL_PROMPTS_JSON):
                prompts = _load_json(LOCAL_PROMPTS_JSON, [])
                report_lines.append(f"[OK] Local prompts JSON loaded: {len(prompts)} presets.")
                with_img = sum(1 for p in prompts if _get_prompt_image_path(p))
                report_lines.append(f"[OK] Presets with local images: {with_img}/{len(prompts)}.")
            else:
                report_lines.append("[WARN] local_prompts.json not found. Run build_local_prompts.py or Updater node.")
                healthy = False

            if os.path.exists(IMAGES_DIR):
                img_folders = [f for f in os.listdir(IMAGES_DIR) if os.path.isdir(os.path.join(IMAGES_DIR, f))]
                report_lines.append(f"[OK] Images directory: {len(img_folders)} folders.")
            else:
                report_lines.append("[WARN] Images directory not found.")
                healthy = False

            customs = _load_json(CUSTOM_PROMPTS_JSON, [])
            report_lines.append(f"[OK] Custom prompts: {len(customs)}.")

            state = _load_json(UPDATE_STATE_FILE, {})
            if state.get("last_update_time"):
                report_lines.append(f"[OK] Last update: {state['last_update_time']}.")
            else:
                report_lines.append("[INFO] Never rebuilt from README.")

        # 3. Network check (verify GitHub repo is accessible for future updates)
        if check_network:
            try:
                test_url = f"{GITHUB_RAW_BASE}/README.md"
                req = urllib.request.Request(test_url, method="HEAD",
                                            headers={"User-Agent": "ComfyUI-GPTImage2Prompt/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    report_lines.append(f"[OK] GitHub accessible (HTTP {resp.status}).")
            except Exception as e:
                report_lines.append(f"[WARN] GitHub not accessible: {e}")
                healthy = False

        # 4. Passthrough check
        if passthrough_string:
            report_lines.append(f"[OK] Passthrough string received ({len(passthrough_string)} chars).")

        report = "\n".join(report_lines)
        return {
            "ui": {
                "status_report": [report],
                "is_healthy": [healthy],
            },
            "result": (report, healthy,),
        }


# ============================================================
# Node: GPT Image 2 Prompt Preview (provides thumbnail info to frontend)
# ============================================================
class GPTImage2PromptPreview:
    """Display thumbnail preview for the selected prompt. All images served locally."""

    CATEGORY = "GPT Image 2 Prompts"
    FUNCTION = "preview_prompt"
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("prompt", "image_path",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        choices = _get_prompt_choices()
        categories = _get_categories()
        return {
            "required": {
                "category": (categories, {"default": "all"}),
                "prompt_selection": (choices, {"default": choices[0]}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def preview_prompt(self, prompt_selection, category="all"):
        prompt_data, prompt_text, image_abs_path = _parse_selection(prompt_selection)
        image_rel = prompt_data.get("image_path", "") if prompt_data else ""

        return {
            "ui": {
                "image_path": [image_rel],
                "text": [prompt_text],
            },
            "result": (prompt_text, image_rel,),
        }


# ============================================================
# Registration
# ============================================================
NODE_CLASS_MAPPINGS = {
    "GPTImage2PromptSelector": GPTImage2PromptSelector,
    "GPTImage2PromptUpdater": GPTImage2PromptUpdater,
    "GPTImage2CustomPromptSaver": GPTImage2CustomPromptSaver,
    "GPTImage2ExecutionChecker": GPTImage2ExecutionChecker,
    "GPTImage2PromptPreview": GPTImage2PromptPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GPTImage2PromptSelector": "GPT Image 2 Prompt Selector 🎨",
    "GPTImage2PromptUpdater": "GPT Image 2 Prompt Updater 🔄",
    "GPTImage2CustomPromptSaver": "GPT Image 2 Custom Prompt Saver 💾",
    "GPTImage2ExecutionChecker": "GPT Image 2 Execution Checker ✅",
    "GPTImage2PromptPreview": "GPT Image 2 Prompt Preview 🖼️",
}
