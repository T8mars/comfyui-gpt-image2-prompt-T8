"""
ComfyUI GPT Image 2 Prompt - Server API Routes
Serves local images from NODE_DIR/data/images/ directory.
All thumbnails are local files - fully self-contained, no repo root dependency.
"""

import os
import json
import mimetypes
import server
from aiohttp import web

from .nodes import (
    NODE_DIR, DATA_DIR, IMAGES_DIR, IMAGE_BASE, LOCAL_PROMPTS_JSON,
    CUSTOM_PROMPTS_DIR, CUSTOM_PROMPTS_JSON, UPDATE_STATE_FILE,
    _load_json, _save_json, _load_all_prompts,
    _get_prompt_image_path, _parse_selection, _get_prompt_choices,
    _get_categories
)

print(f"[GPTImage2Prompt] API routes loading. NODE_DIR={NODE_DIR}")
print(f"[GPTImage2Prompt] IMAGES_DIR={IMAGES_DIR}, exists={os.path.exists(IMAGES_DIR)}")


def _get_image_rel_for_prompt(prompt_data):
    """Get the relative image path (from DATA_DIR) for a prompt, handling both formats."""
    if not prompt_data:
        return ""
    # New format: image_path relative to DATA_DIR
    image_rel = prompt_data.get("image_path", "")
    if image_rel:
        return image_rel
    # Legacy format: absolute thumbnail path → convert to relative
    thumb = prompt_data.get("thumbnail", "")
    if thumb and os.path.isfile(thumb):
        try:
            return os.path.relpath(thumb, DATA_DIR).replace(os.sep, "/")
        except ValueError:
            return ""
    return ""


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/prompts")
async def get_prompts(request):
    """Return all prompts (preset + custom) as JSON."""
    presets, customs = _load_all_prompts()
    return web.json_response({
        "presets": presets,
        "customs": customs,
        "total": len(presets) + len(customs),
    })


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/choices_by_category")
async def get_choices_by_category(request):
    """Return prompt choices grouped by category for frontend filtering."""
    presets, customs = _load_all_prompts()
    result = {}  # category -> list of {index, label, has_image}

    for i, p in enumerate(presets):
        cat = p.get("category", "other")
        title = p.get("title", "")
        author = p.get("author", "")
        text_preview = p.get("text", "")[:60].replace("\n", " ")
        label = f"[{cat}] {title}" if title else f"[{cat}] {text_preview}"
        if author:
            label += f" (@{author})"
        choice_str = f"[preset_{i}] {label}"

        image_rel = p.get("image_path", "")
        has_img = False
        if image_rel:
            full = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
            has_img = os.path.isfile(full)

        entry = {"value": choice_str, "has_image": has_img}
        result.setdefault(cat, []).append(entry)
        result.setdefault("all", []).append(entry)

    for i, p in enumerate(customs):
        name = p.get("name", p.get("text", "")[:50])
        choice_str = f"[custom_{i}] {name}"
        image_rel = _get_image_rel_for_prompt(p)
        has_img = False
        if image_rel:
            full = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
            has_img = os.path.isfile(full)
        entry = {"value": choice_str, "has_image": has_img}
        result.setdefault("custom", []).append(entry)
        result.setdefault("all", []).append(entry)

    return web.json_response(result)


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/prompt/{prompt_type}/{index}")
async def get_prompt_detail(request):
    """Return a single prompt by type and index."""
    prompt_type = request.match_info["prompt_type"]
    try:
        index = int(request.match_info["index"])
    except ValueError:
        return web.json_response({"error": "Invalid index"}, status=400)

    if prompt_type == "preset":
        prompts = _load_json(LOCAL_PROMPTS_JSON, [])
    elif prompt_type == "custom":
        prompts = _load_json(CUSTOM_PROMPTS_JSON, [])
    else:
        return web.json_response({"error": "Invalid type"}, status=400)

    if 0 <= index < len(prompts):
        p = prompts[index]
        return web.json_response(p)
    return web.json_response({"error": "Index out of range"}, status=404)


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/resolve_selection")
async def resolve_selection(request):
    """Given a prompt_selection string, return full text + local image path + metadata."""
    selection = request.query.get("selection", "")
    if not selection:
        return web.json_response({"error": "No selection parameter"}, status=400)

    prompt_data, prompt_text, image_abs_path = _parse_selection(selection)
    image_rel = _get_image_rel_for_prompt(prompt_data)
    title = prompt_data.get("title", prompt_data.get("name", "")) if prompt_data else ""
    category = prompt_data.get("category", "") if prompt_data else ""

    # has_image: check the relative path exists in data/ directory
    has_image = False
    if image_rel:
        full_path = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
        has_image = os.path.isfile(full_path)

    return web.json_response({
        "text": prompt_text,
        "image_path": image_rel,
        "has_image": has_image,
        "title": title,
        "category": category,
    })


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/refresh_choices")
async def refresh_choices(request):
    """Return fresh choices and categories for frontend refresh (no restart needed)."""
    choices = _get_prompt_choices()
    categories = _get_categories()

    # Also return grouped choices
    presets, customs = _load_all_prompts()
    grouped = {}
    for i, p in enumerate(presets):
        cat = p.get("category", "other")
        title = p.get("title", "")
        author = p.get("author", "")
        text_preview = p.get("text", "")[:60].replace("\n", " ")
        label = f"[{cat}] {title}" if title else f"[{cat}] {text_preview}"
        if author:
            label += f" (@{author})"
        choice_str = f"[preset_{i}] {label}"
        image_rel = p.get("image_path", "")
        has_img = False
        if image_rel:
            full = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
            has_img = os.path.isfile(full)
        entry = {"value": choice_str, "has_image": has_img}
        grouped.setdefault(cat, []).append(entry)
        grouped.setdefault("all", []).append(entry)

    for i, p in enumerate(customs):
        name = p.get("name", p.get("text", "")[:50])
        choice_str = f"[custom_{i}] {name}"
        image_rel = _get_image_rel_for_prompt(p)
        has_img = False
        if image_rel:
            full = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
            has_img = os.path.isfile(full)
        entry = {"value": choice_str, "has_image": has_img}
        grouped.setdefault("custom", []).append(entry)
        grouped.setdefault("all", []).append(entry)

    return web.json_response({
        "choices": choices,
        "categories": categories,
        "grouped": grouped,
    })


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/image")
async def serve_local_image_query(request):
    """Serve an image using query parameter.
    URL format: /gpt_image2_prompt/image?path=images/portrait_case1/output.jpg
    Also supports path parameter: /gpt_image2_prompt/image?path=images/...
    """
    rel_path = request.query.get("path", "")
    if not rel_path:
        return web.Response(status=400, text="Missing 'path' query parameter")
    return _serve_image_file(rel_path)


def _serve_image_file(rel_path):
    """Serve image from NODE_DIR/data/ directory."""
    if not rel_path:
        return web.Response(status=400, text="Empty path")

    # Security: no path traversal
    if ".." in rel_path:
        return web.Response(status=403, text="Forbidden")

    # Normalize path separators to OS-native
    rel_path_clean = rel_path.replace("\\", "/").replace("/", os.sep)

    # Resolve to absolute path within IMAGE_BASE (= DATA_DIR)
    abs_path = os.path.normpath(os.path.join(IMAGE_BASE, rel_path_clean))

    # Ensure it's still within NODE_DIR (prevent traversal)
    node_norm = os.path.normpath(NODE_DIR)
    if not abs_path.startswith(node_norm):
        print(f"[GPTImage2Prompt] SECURITY: path outside node dir: {abs_path}")
        return web.Response(status=403, text="Forbidden")

    if os.path.isfile(abs_path):
        ct, _ = mimetypes.guess_type(abs_path)
        if not ct:
            ct = "image/jpeg"
        return web.FileResponse(abs_path, headers={
            "Content-Type": ct,
            "Cache-Control": "public, max-age=86400",
        })

    # Not found - log details for debugging
    print(f"[GPTImage2Prompt] Image NOT FOUND:")
    print(f"  rel_path={rel_path}")
    print(f"  abs_path={abs_path}")
    print(f"  IMAGE_BASE={IMAGE_BASE}")

    # Try alternative: resolve directly under IMAGES_DIR
    if not rel_path_clean.startswith("images"):
        alt_path = os.path.normpath(os.path.join(IMAGES_DIR, rel_path_clean))
        if os.path.isfile(alt_path):
            ct, _ = mimetypes.guess_type(alt_path)
            if not ct:
                ct = "image/jpeg"
            return web.FileResponse(alt_path, headers={"Content-Type": ct})

    return web.Response(status=404, text=f"Image not found: {rel_path}")


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/categories")
async def get_categories(request):
    """Return available prompt categories with counts."""
    presets, customs = _load_all_prompts()
    categories = {}
    for p in presets:
        cat = p.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    categories["custom"] = len(customs)
    categories["all"] = len(presets) + len(customs)
    return web.json_response(categories)


@server.PromptServer.instance.routes.post("/gpt_image2_prompt/delete_custom/{index}")
async def delete_custom_prompt(request):
    """Delete a custom prompt by index."""
    try:
        index = int(request.match_info["index"])
    except ValueError:
        return web.json_response({"error": "Invalid index"}, status=400)

    customs = _load_json(CUSTOM_PROMPTS_JSON, [])
    if 0 <= index < len(customs):
        removed = customs.pop(index)
        # Delete associated image file (supports both new 'image_path' and legacy 'thumbnail')
        image_rel = removed.get("image_path", "")
        if image_rel:
            img_abs = os.path.normpath(os.path.join(IMAGE_BASE, image_rel))
            if os.path.exists(img_abs):
                try:
                    os.remove(img_abs)
                except Exception:
                    pass
        else:
            thumb = removed.get("thumbnail", "")
            if thumb and os.path.exists(thumb):
                try:
                    os.remove(thumb)
                except Exception:
                    pass
        _save_json(CUSTOM_PROMPTS_JSON, customs)
        return web.json_response({"status": "deleted", "remaining": len(customs)})
    return web.json_response({"error": "Index out of range"}, status=404)


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/status")
async def get_status(request):
    """Return current plugin status info."""
    state = _load_json(UPDATE_STATE_FILE, {})
    presets, customs = _load_all_prompts()
    with_images = sum(1 for p in presets if _get_prompt_image_path(p))

    return web.json_response({
        "preset_count": len(presets),
        "custom_count": len(customs),
        "presets_with_images": with_images,
        "last_update": state.get("last_update_time", "Never"),
        "images_dir": IMAGES_DIR,
        "images_dir_exists": os.path.exists(IMAGES_DIR),
        "node_dir": NODE_DIR,
    })


@server.PromptServer.instance.routes.get("/gpt_image2_prompt/debug_image")
async def debug_image(request):
    """Debug endpoint to verify image path resolution."""
    rel_path = request.query.get("path", "images/portrait_case1/output.jpg")
    abs_path = os.path.normpath(os.path.join(IMAGE_BASE, rel_path))
    return web.json_response({
        "rel_path": rel_path,
        "abs_path": abs_path,
        "image_base": IMAGE_BASE,
        "node_dir": NODE_DIR,
        "exists": os.path.isfile(abs_path),
        "images_dir_exists": os.path.isdir(IMAGES_DIR),
    })
