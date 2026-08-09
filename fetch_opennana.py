#!/usr/bin/env python3
"""
Fetch prompt templates from opennana.com and add them incrementally
to the local_prompts.json file.

Usage:
    # Fetch ALL prompts from sitemap (incremental)
    python fetch_opennana.py --all

    # Fetch by slug(s)
    python fetch_opennana.py --slugs korean-street-ootd,playful-doodle-overlay

    # Fetch by numeric ID(s) (legacy prompt-NNN format)
    python fetch_opennana.py --ids 515,601,805

    # Dry-run (parse only, no download)
    python fetch_opennana.py --all --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path

try:
    from .http_retry import read_url_with_retry
except ImportError:
    from http_retry import read_url_with_retry

# ---------------------------------------------------------------------------
# Paths (all str, no pathlib at runtime — Windows compatibility)
# ---------------------------------------------------------------------------
NODE_DIR = str(Path(__file__).resolve().parent)
DATA_DIR = os.path.join(NODE_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
LOCAL_PROMPTS_JSON = os.path.join(DATA_DIR, "local_prompts.json")

OPENNANA_DETAIL = "https://opennana.com/awesome-prompt-gallery/{slug}"
OPENNANA_IMG_NUM = "https://img.opennana.com/prompts/images/{id}.jpeg"
OPENNANA_SITEMAP = "https://opennana.com/sitemap.xml"
GALLERY_PREFIX = "https://opennana.com/awesome-prompt-gallery/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

# Tag -> category mapping (opennana tags → our categories)
TAG_CATEGORY_MAP = {
    "portrait": "portrait",
    "photography": "portrait",
    "fashion": "portrait",
    "3d": "character",
    "toy": "character",
    "fantasy": "character",
    "anime": "character",
    "character": "character",
    "poster": "poster",
    "typography": "poster",
    "food": "poster",
    "interior": "poster",
    "nature": "poster",
    "ui": "ui",
    "design": "ui",
    "comparison": "comparison",
    "vehicle": "poster",
    "animal": "poster",
    "product": "ecommerce",
    "ecommerce": "ecommerce",
    "ad": "ad_creative",
}

# Slug keyword -> category mapping (used when tags are empty)
SLUG_CATEGORY_RULES = [
    ("portrait", ["portrait", "selfie", "girl", "woman", "model", "beauty", "blonde",
                  "redhead", "billie", "jennie", "sweeney", "kpop", "boudoir",
                  "workout", "gym", "sweaty", "stretch", "poolside", "bikini",
                  "wet_look", "wet_gaze", "mirror_selfie", "flirty", "muse",
                  "duo", "gaze", "glance", "goddess", "samurai", "fashion_model",
                  "blazer_woman", "red_dress", "satin", "carpet", "athleisure",
                  "driving", "sofa", "bedding", "attic", "cafe", "bus_window",
                  "bath", "recording_video", "dresses", "ootd", "film_girl",
                  "film_dream", "sweet_pink", "glass_skin", "gentle_touch",
                  "waterfall_cave", "silent_rhythm", "street_flash",
                  "convenience_store", "midnight_beach", "sunny_beach",
                  "sunlit_bedroom", "honey_blonde", "hilarious_back",
                  "tropical_island", "lazy_afternoon", "balcony_neon",
                  "red_carpet", "hourglass", "campus_graduation", "vacation",
                  "beach", "sunset", "lazy"]),
    ("character", ["anime", "character", "3d_cartoon", "emoji_sticker",
                   "doodle", "snail", "mascot", "yuji_sword",
                   "double_exposure_anime", "hairstyle_design",
                   "white_handwritten_profile"]),
    ("poster", ["poster", "collage", "blueprint", "schematic", "map",
                "infographic", "book_interior", "naming_poster",
                "ink_guangzhou", "candle_moonlit", "quad_panel",
                "gallery_abstract", "bmw", "neon_x_brand",
                "neon_dark_future", "winter_wonderland"]),
    ("ecommerce", ["product", "soda", "sprite", "coffee_art", "crepe",
                   "ice_cream", "burger", "perfume", "loafer",
                   "balloon_skincare", "watch", "macaron", "mascara"]),
    ("ad_creative", ["ad", "campaign", "pitch", "startup"]),
    ("ui", ["ui", "booth"]),
]


def _fetch_page(url):
    """Fetch HTML content from a URL."""
    try:
        return read_url_with_retry(
            url,
            headers=HEADERS,
            timeout=30,
        ).decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  [ERROR] HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  [ERROR] {e} fetching {url}")
        return None


def _download_image(url, save_path):
    """Download an image to local path."""
    try:
        data = read_url_with_retry(url, headers=HEADERS, timeout=60)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(data)
        print(f"  [OK] Image saved: {save_path} ({len(data)} bytes)")
        return True
    except Exception as e:
        print(f"  [ERROR] Image download failed: {e}")
        return False


def fetch_sitemap_slugs():
    """
    Fetch sitemap.xml and extract all gallery prompt slugs.
    Returns list of slug strings.
    """
    print("Fetching sitemap.xml ...")
    xml = _fetch_page(OPENNANA_SITEMAP)
    if not xml:
        print("[ERROR] Could not fetch sitemap.xml")
        return []

    # Extract all <loc> URLs that are gallery prompt pages
    all_locs = re.findall(r'<loc>(https://opennana\.com/awesome-prompt-gallery/[^<]+)</loc>', xml)
    slugs = []
    for loc in all_locs:
        slug = loc.replace(GALLERY_PREFIX, "").strip("/")
        # Skip the gallery index page itself
        if slug and slug != "awesome-prompt-gallery" and not slug.startswith("?"):
            slugs.append(slug)

    print(f"  Found {len(slugs)} prompt pages in sitemap")
    return slugs


def parse_prompt_page(slug_or_id):
    """
    Parse a single prompt detail page from opennana.com.
    Accepts slug (e.g. 'korean-street-ootd') or numeric ID (e.g. 515).
    Returns dict with: slug, title, author, text, tags, image_url
    """
    # Determine URL format
    is_numeric = str(slug_or_id).isdigit()
    if is_numeric:
        slug = f"prompt-{slug_or_id}"
        url = OPENNANA_DETAIL.format(slug=slug)
    else:
        slug = str(slug_or_id)
        url = OPENNANA_DETAIL.format(slug=slug)

    print(f"  Fetching {url} ...")
    html = _fetch_page(url)
    if not html:
        return None

    result = {
        "slug": slug,
        "title": "",
        "author": "",
        "text": "",
        "tags": [],
        "image_url": "",
    }

    # --- Extract title ---
    title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if not title_match:
        title_match = re.search(r'<title>([^|<]+)', html)
    if title_match:
        result["title"] = title_match.group(1).strip()
    else:
        og_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if og_match:
            result["title"] = og_match.group(1).strip()

    # Clean title - remove suffix like " | Nano banana pro AI提示词 | OpenNana"
    result["title"] = re.sub(r'\s*\|.*$', '', result["title"]).strip()

    # --- Extract author ---
    author_match = re.search(r'来源.*?@(\w+)', html)
    if not author_match:
        author_match = re.search(r'source.*?@(\w+)', html, re.IGNORECASE)
    if author_match:
        result["author"] = author_match.group(1)

    # --- Extract prompt text (English version, in code block) ---
    code_blocks = re.findall(r'```\s*\n(.*?)```', html, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r'<(?:code|pre)[^>]*>(.*?)</(?:code|pre)>', html, re.DOTALL)

    if code_blocks:
        for block in code_blocks:
            text = block.strip()
            if len(text) > 20:
                result["text"] = _clean_html(text)
                break

    # --- Extract tags ---
    # Meta keywords (most reliable)
    kw_match = re.search(r'<meta\s+name="keywords"\s+content="([^"]+)"', html)
    if kw_match:
        raw_kw = kw_match.group(1)
        result["tags"] = [t.strip().lower() for t in raw_kw.split(",") if t.strip()]

    # Fallback: from page content "收藏..." section
    if not result["tags"]:
        tags_match = re.search(r'收藏([\w\s]+?)(?:\n|<|$)', html)
        if tags_match:
            result["tags"] = re.findall(r'[a-z]+', tags_match.group(1).lower())

    # --- Extract image URL ---
    # Try og:image first
    og_img = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
    if og_img:
        result["image_url"] = og_img.group(1)

    # Try image in page body
    if not result["image_url"]:
        img_match = re.search(r'(https?://img\.opennana\.com/prompts/images/[^"\s<>]+)', html)
        if img_match:
            result["image_url"] = img_match.group(1)

    # Try numeric ID pattern
    if not result["image_url"] and is_numeric:
        result["image_url"] = OPENNANA_IMG_NUM.format(id=slug_or_id)

    # Try extracting numeric ID from image URL or page for slug-based pages
    if not result["image_url"]:
        num_match = re.search(r'img\.opennana\.com/prompts/images/(\d+)\.', html)
        if num_match:
            result["image_url"] = f"https://img.opennana.com/prompts/images/{num_match.group(1)}.jpeg"

    return result


def _clean_html(text):
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    text = text.replace('&nbsp;', ' ')
    return text.strip()


def _infer_category(tags, slug=""):
    """Infer category from opennana tags, falling back to slug keywords."""
    # Try tag-based mapping first
    for tag in tags:
        if tag in TAG_CATEGORY_MAP:
            return TAG_CATEGORY_MAP[tag]
    # Fall back to slug keyword matching
    slug_lower = slug.lower().replace("-", "_")
    for cat, keywords in SLUG_CATEGORY_RULES:
        for kw in keywords:
            if kw in slug_lower:
                return cat
    return "portrait"  # default for opennana (mostly portrait/photography)


def _load_existing():
    """Load existing local_prompts.json."""
    if not os.path.isfile(LOCAL_PROMPTS_JSON):
        return []
    try:
        with open(LOCAL_PROMPTS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json(data):
    """Save data to local_prompts.json."""
    os.makedirs(os.path.dirname(LOCAL_PROMPTS_JSON), exist_ok=True)
    with open(LOCAL_PROMPTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_prompt(slug_or_id, entries, existing_ids, dry_run=False):
    """
    Fetch a single prompt from opennana.com and add it to entries list.
    Returns True on success. Caller is responsible for saving.
    """
    # Build entry_id from slug
    slug_str = str(slug_or_id)
    entry_id = f"opennana_{slug_str.replace('-', '_')}"

    # Check if already exists
    if entry_id in existing_ids:
        return False  # silent skip

    # Parse the page
    parsed = parse_prompt_page(slug_or_id)
    if not parsed:
        print(f"  [FAIL] Could not parse {slug_or_id}")
        return False

    if not parsed["text"]:
        print(f"  [WARN] No prompt text for {slug_or_id}")

    # Determine category
    category = _infer_category(parsed["tags"], slug_str)

    # Image local path
    img_folder = f"opennana_{slug_str.replace('-', '_')}"
    img_rel_path = f"images/{img_folder}/output.jpg"
    img_abs_path = os.path.join(IMAGES_DIR, img_folder, "output.jpg")

    # Determine image extension from URL
    img_url = parsed["image_url"]
    if img_url:
        ext_match = re.search(r'\.(jpe?g|png|webp|gif)(\?|$)', img_url, re.IGNORECASE)
        if ext_match:
            ext = ext_match.group(1).lower()
            if ext == "jpeg":
                ext = "jpg"
            img_rel_path = f"images/{img_folder}/output.{ext}"
            img_abs_path = os.path.join(IMAGES_DIR, img_folder, f"output.{ext}")

    title = parsed["title"] or slug_str.replace("-", " ").title()
    text_preview = parsed['text'][:80] + '...' if len(parsed.get('text', '')) > 80 else parsed.get('text', '(none)')
    print(f"  [{slug_str}] {title} | {category} | img={'Y' if img_url else 'N'} | text={len(parsed.get('text',''))}ch")

    if dry_run:
        return True

    # Download image
    img_ok = False
    if img_url:
        img_ok = _download_image(img_url, img_abs_path)

    # Build entry
    new_entry = {
        "id": entry_id,
        "category": category,
        "case_num": 0,
        "title": title,
        "author": parsed["author"],
        "text": parsed["text"],
        "image_path": img_rel_path,
        "image_exists": img_ok,
        "source": f"opennana.com/{slug_str}",
    }

    entries.append(new_entry)
    existing_ids.add(entry_id)
    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch prompts from opennana.com")
    parser.add_argument("--all", action="store_true", help="Fetch all prompts from sitemap (incremental)")
    parser.add_argument("--slugs", type=str, help="Comma-separated slugs (e.g. korean-street-ootd,playful-doodle-overlay)")
    parser.add_argument("--ids", type=str, help="Comma-separated numeric IDs (legacy prompt-NNN format)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't download or save")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds (default: 1.5)")
    args = parser.parse_args()

    # Build target list
    targets = []
    if args.all:
        targets = fetch_sitemap_slugs()
    elif args.slugs:
        targets = [s.strip() for s in args.slugs.split(",") if s.strip()]
    elif args.ids:
        targets = [x.strip() for x in args.ids.split(",") if x.strip().isdigit()]

    if not targets:
        print("Usage:")
        print("  python fetch_opennana.py --all              # Fetch all from sitemap")
        print("  python fetch_opennana.py --slugs slug1,slug2")
        print("  python fetch_opennana.py --ids 515,601")
        sys.exit(1)

    result = sync_from_opennana(targets=targets, dry_run=args.dry_run, delay=args.delay)
    print(f"\n=== Done ===")
    print(f"  Added:   {result['added']}")
    print(f"  Skipped: {result['skipped']} (already exist)")
    print(f"  Failed:  {result['failed']}")
    print(f"  Total:   {result['old_count']} -> {result['new_count']} entries")


def sync_from_opennana(targets=None, dry_run=False, delay=1.0):
    """
    Sync prompts from opennana.com. Can be called programmatically (e.g. from nodes.py).

    Args:
        targets: list of slugs/ids. If None, fetches all from sitemap.
        dry_run: if True, don't download images or save JSON.
        delay: seconds between HTTP requests.

    Returns:
        dict with keys: added, skipped, failed, old_count, new_count, message
    """
    # Fetch sitemap targets if not provided
    if targets is None:
        targets = fetch_sitemap_slugs()

    if not targets:
        return {"added": 0, "skipped": 0, "failed": 0,
                "old_count": 0, "new_count": 0,
                "message": "No targets found in sitemap"}

    # Load existing data once
    entries = _load_existing()
    existing_ids = {e.get("id", "") for e in entries}
    initial_count = len(entries)

    print(f"=== OpenNana Prompt Sync ===")
    print(f"Targets:    {len(targets)} pages")
    print(f"Existing:   {initial_count} entries ({len([e for e in existing_ids if 'opennana' in e])} from opennana)")
    print(f"Delay:      {delay}s between requests")
    print(f"Dry-run:    {dry_run}")
    print()

    success = 0
    skipped = 0
    failed = 0
    for i, target in enumerate(targets):
        # Quick skip check before fetching
        slug_str = str(target)
        entry_id = f"opennana_{slug_str.replace('-', '_')}"
        if entry_id in existing_ids:
            skipped += 1
            continue

        try:
            if add_prompt(target, entries, existing_ids, dry_run=dry_run):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [ERROR] {target}: {e}")
            failed += 1

        # Progress report every 10
        if (success + failed) % 10 == 0 and (success + failed) > 0:
            print(f"  --- Progress: {success} added, {skipped} skipped, {failed} failed / {len(targets)} total ---")

        # Be polite to the server
        if i < len(targets) - 1:
            time.sleep(delay)

    # Save once at the end (not per-entry)
    if success > 0 and not dry_run:
        _save_json(entries)
        print(f"\n  Saved {len(entries)} entries to {LOCAL_PROMPTS_JSON}")

    msg_parts = []
    msg_parts.append(f"OpenNana sync: {len(targets)} pages checked")
    if success > 0:
        msg_parts.append(f"{success} new prompts added")
    if skipped > 0:
        msg_parts.append(f"{skipped} already exist")
    if failed > 0:
        msg_parts.append(f"{failed} failed")

    return {
        "added": success,
        "skipped": skipped,
        "failed": failed,
        "old_count": initial_count,
        "new_count": len(entries),
        "message": ", ".join(msg_parts),
    }


if __name__ == "__main__":
    main()
