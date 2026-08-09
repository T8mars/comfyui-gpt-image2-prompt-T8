"""
Parse ALL README files (English + translations) to extract cases with prompts and local images.
Generates a local_prompts.json and copies all referenced images into data/images/.
After build, the node directory is fully self-contained.
"""
import re
import os
import json
import shutil
from pathlib import Path

try:
    from .http_retry import read_url_with_retry
except ImportError:
    from http_retry import read_url_with_retry

NODE_DIR = Path(__file__).resolve().parent            # comfyui-gpt-image2-prompt/

# Source images: NODE_DIR/images/ (self-contained install)
# Use os.path.isdir for reliable Windows path checking
SRC_IMAGES_DIR = str(NODE_DIR / "images")

LOCAL_IMAGES_DIR = str(NODE_DIR / "data" / "images")  # Destination inside node dir
OUTPUT_JSON = str(NODE_DIR / "data" / "local_prompts.json")

# GitHub raw base URL for downloading README files
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/EvoLinkAI/awesome-gpt-image-2-API-and-Prompts/main"

# Section keyword mapping (works across languages)
SECTION_KEYWORDS = {
    "portrait": ["portrait", "photo", "retrato", "portr", "ritratt", "photography"],
    "poster": ["poster", "illustration", "cartel", "affiche", "plakat"],
    "character": ["character", "personaje", "personnage", "karakter", "charakt"],
    "ui": ["ui", "social media", "mockup", "interfaz", "maquette"],
    "comparison": ["comparison", "community", "comparaci", "comparais", "vergleich"],
    "ecommerce": ["e-commerce", "ecommerce", "comercio", "e-kommerz"],
    "ad_creative": ["ad creative", "ad-creative", "publicidad", "werbung", "publicit"],
}


def detect_section(line):
    """Detect section category from a ## heading line."""
    line_lower = line.lower()
    for cat, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in line_lower:
                return cat
    return None


def parse_single_readme(readme_path, existing_image_paths):
    """Parse one README file, return list of case dicts.
    existing_image_paths: set of image_path already found, to avoid duplicates.
    Accepts cases with image even if prompt is empty.
    """
    if isinstance(readme_path, Path):
        content = readme_path.read_text(encoding="utf-8")
    else:
        content = readme_path  # Already string content (e.g. downloaded)
    lines = content.split("\n")
    cases = []
    current_section = "other"
    i = 0
    source_name = readme_path.name if isinstance(readme_path, Path) else "downloaded"

    while i < len(lines):
        line = lines[i]

        # Detect section headings (## level)
        if line.startswith("## "):
            detected = detect_section(line)
            if detected:
                current_section = detected

        # Detect case heading: ### Case N:
        case_match = re.match(r'###\s*Case\s+(\d+):', line)
        if case_match:
            case_num = case_match.group(1)

            # Extract title
            title_match = re.search(r'\[([^\]]+)\]', line)
            title = title_match.group(1) if title_match else f"Case {case_num}"

            # Extract author
            author_match = re.search(r'by\s*\[@?([^\])\s]+)', line)
            author = author_match.group(1) if author_match else ""

            # Look ahead for image path and prompt (search up to 50 lines)
            image_path = ""
            prompt_text = ""
            found_prompt_block = False
            j = i + 1
            while j < len(lines) and j < i + 50:
                # Stop if we hit the next case heading
                if re.match(r'###\s*Case\s+\d+:', lines[j]):
                    break

                # Find image - match HTML src="./images/..." AND Markdown ![...](images/...)
                if not image_path:
                    img_match = re.search(r'src="\.?/?\s*(images/[^"]+)"', lines[j])
                    if img_match:
                        image_path = img_match.group(1)
                    else:
                        md_match = re.search(r'!\[[^\]]*\]\(\.?/?\s*(images/[^)]+)\)', lines[j])
                        if md_match:
                            image_path = md_match.group(1)

                # Find prompt code block (``` after **Prompt** section)
                if lines[j].strip() == "```" and not found_prompt_block:
                    found_prompt_block = True
                    k = j + 1
                    prompt_lines = []
                    while k < len(lines):
                        if lines[k].strip() == "```":
                            break
                        prompt_lines.append(lines[k])
                        k += 1
                    if prompt_lines:
                        prompt_text = "\n".join(prompt_lines).strip()
                    j = k  # Skip past the closing ```
                j += 1

            # Accept case if we have image path (prompt may be empty)
            if image_path and image_path not in existing_image_paths:
                # Check if image exists locally (for status tracking)
                img_exists = _check_image_exists(image_path)

                # Infer category from image folder name if section is generic
                folder_name = image_path.split("/")[1] if "/" in image_path else ""
                if current_section == "other" and folder_name:
                    inferred = _infer_category_from_folder(folder_name)
                    if inferred != "other":
                        current_section = inferred

                cases.append({
                    "id": f"{current_section}_case{case_num}",
                    "category": current_section,
                    "case_num": int(case_num),
                    "title": title[:200],
                    "author": author,
                    "text": prompt_text,
                    "image_path": image_path,
                    "image_exists": img_exists,
                    "source": source_name,
                })
                existing_image_paths.add(image_path)

        i += 1

    return cases


def _check_image_exists(image_rel_path):
    """Check if an image exists in any known location within NODE_DIR."""
    candidates = [
        os.path.join(SRC_IMAGES_DIR, os.sep.join(image_rel_path.split("/")[1:])),  # images/xxx -> SRC/xxx
        os.path.join(str(NODE_DIR), image_rel_path.replace("/", os.sep)),
        os.path.join(LOCAL_IMAGES_DIR, os.sep.join(image_rel_path.split("/")[1:])),  # Already in data/images/
    ]
    for p in candidates:
        if os.path.isfile(p):
            return True
    return False


def _infer_category_from_folder(folder_name):
    """Infer category from folder name prefix like 'portrait_case1'."""
    for prefix in ["portrait", "poster", "character", "ui", "comparison", "ecommerce", "ad_creative"]:
        if folder_name.startswith(prefix + "_"):
            return prefix
    # Additional prefix patterns
    if folder_name.startswith("ad_"):
        return "ad_creative"
    if folder_name.startswith("ecom_"):
        return "ecommerce"
    return "other"


def _find_best_image(folder_path):
    """Find the best image file in a folder (prefer output.jpg)."""
    folder_str = str(folder_path)
    if not os.path.isdir(folder_str):
        return ""
    files = os.listdir(folder_str)
    # Priority order
    for name in ["output.jpg", "output.png"]:
        if name in files:
            return name
    # Then output*.jpg/png
    for f in sorted(files):
        if f.startswith("output") and (f.endswith(".jpg") or f.endswith(".png")):
            return f
    # Then any image
    for f in sorted(files):
        if f.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return f
    return ""


def _build_md5_map():
    """Build MD5 hash map for all output.jpg files in source images/ directory."""
    import hashlib
    md5_map = {}  # hash -> list of folder names
    if not os.path.isdir(SRC_IMAGES_DIR):
        return md5_map
    for folder_name in os.listdir(SRC_IMAGES_DIR):
        img = os.path.join(SRC_IMAGES_DIR, folder_name, "output.jpg")
        if os.path.isfile(img):
            with open(img, "rb") as f:
                h = hashlib.md5(f.read()).hexdigest()
            md5_map.setdefault(h, []).append(folder_name)
    return md5_map


def _list_github_image_folders():
    """List image folders from GitHub API (when local images/ doesn't exist)."""
    url = "https://api.github.com/repos/EvoLinkAI/awesome-gpt-image-2-API-and-Prompts/contents/images"
    try:
        payload = read_url_with_retry(
            url,
            headers={
                "User-Agent": "ComfyUI-GPTImage2Prompt/1.0",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=30,
        )
        import json as _json
        items = _json.loads(payload.decode("utf-8"))
        folders = [item["name"] for item in items if item["type"] == "dir"]
        return folders
    except Exception as e:
        print(f"  [Warning] GitHub API listing failed: {e}")
        return []


def scan_images_directory(existing_image_paths):
    """Scan images/ directory for any folders not yet covered.
    Creates entries for uncovered folders (image-only, no prompt text from README).
    If local images/ doesn't exist, queries GitHub API for folder list.
    """
    cases = []
    covered_folders = set()
    for img_path in existing_image_paths:
        parts = img_path.split("/")
        if len(parts) >= 2:
            covered_folders.add(parts[1])

    # Get folder list: local or from GitHub API
    if os.path.isdir(SRC_IMAGES_DIR):
        all_folders = sorted(os.listdir(SRC_IMAGES_DIR))
        source = "local"
    else:
        print(f"  Local images/ not found, querying GitHub API...")
        all_folders = _list_github_image_folders()
        source = "github"

    for folder_name in sorted(all_folders):
        if folder_name in covered_folders:
            continue

        # Skip non-case folders
        if folder_name.startswith("."):
            continue

        # For local: verify folder has an image
        if source == "local":
            folder_path = os.path.join(SRC_IMAGES_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
            img_file = _find_best_image(folder_path)
            if not img_file:
                continue
            image_path = f"images/{folder_name}/{img_file}"
        else:
            # For GitHub: assume output.jpg exists (will be downloaded in Stage 4)
            image_path = f"images/{folder_name}/output.jpg"

        category = _infer_category_from_folder(folder_name)

        # Extract case number from folder name if possible
        num_match = re.search(r'case(\d+)', folder_name)
        case_num = int(num_match.group(1)) if num_match else 0

        # Create a human-readable title from folder name
        title = folder_name.replace("_", " ").title()

        cases.append({
            "id": folder_name,
            "category": category,
            "case_num": case_num,
            "title": title,
            "author": "",
            "text": "",  # No prompt text available
            "image_path": image_path,
            "image_exists": False,  # Will be resolved in Stage 4
            "source": f"images_directory_{source}",
        })
        existing_image_paths.add(image_path)

    return cases


def _recover_from_git_history(empty_cases):
    """Try to recover prompt text from older git commits for cases with no prompt.
    Optimized: limits to 15 most recent commits that modified README.md, with overall timeout.
    """
    import subprocess
    import time as _time

    start_time = _time.time()
    MAX_SECONDS = 120  # Hard timeout: 120 seconds max
    MAX_COMMITS = 40  # Check up to 40 most recent commits

    # Map folder -> index in empty_cases
    folder_map = {}
    for idx, case in empty_cases:
        img = case.get("image_path", "")
        if "/" in img:
            folder = img.split("/")[1]
            folder_map[folder] = (idx, case)

    if not folder_map:
        return 0

    print(f"    Looking for {len(folder_map)} missing prompts in git history...")

    # Determine git working directory (NODE_DIR only)
    git_cwd = None
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir"],
                         cwd=str(NODE_DIR), capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            git_cwd = str(NODE_DIR)
    except Exception:
        pass
    if not git_cwd:
        print("    No git repository found, skipping git history recovery")
        return 0

    # Get commits that modified README files
    historical_commits = []
    try:
        r = subprocess.run(["git", "log", "--all", "--oneline", "--format=%H", "--", "README.md"],
                          cwd=git_cwd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            historical_commits = [c for c in r.stdout.strip().split("\n") if c][:MAX_COMMITS]
    except Exception:
        return 0

    if not historical_commits:
        print("    No git commits found for README.md")
        return 0

    print(f"    Scanning {len(historical_commits)} commits...")

    readme_names = ["README.md", "README_de.md", "README_zh-CN.md"]
    recovered = {}

    for ci, commit in enumerate(historical_commits):
        # Check timeout
        if _time.time() - start_time > MAX_SECONDS:
            print(f"    Timeout after {ci} commits, recovered {len(recovered)} so far")
            break

        if len(recovered) == len(folder_map):
            break

        still_missing = [f for f in folder_map if f not in recovered]
        if not still_missing:
            break

        for rf in readme_names:
            if _time.time() - start_time > MAX_SECONDS:
                break
            if not still_missing:
                break
            try:
                r = subprocess.run(["git", "show", f"{commit}:{rf}"],
                                 cwd=git_cwd, capture_output=True, timeout=10)
                if r.returncode != 0:
                    continue
                content = r.stdout.decode("utf-8", errors="replace")
            except Exception:
                continue

            lines = content.split("\n")
            for i, line in enumerate(lines):
                for folder in still_missing:
                    if f"images/{folder}/" not in line or folder in recovered:
                        continue

                    # Look for heading
                    heading = ""
                    for j in range(i - 1, max(0, i - 15), -1):
                        if "### Case" in lines[j] or "## Case" in lines[j]:
                            heading = lines[j].strip()[:120]
                            break

                    # Look forward for ``` prompt block
                    prompt_text = ""
                    for j in range(i + 1, min(len(lines), i + 40)):
                        if lines[j].strip().startswith("```"):
                            if lines[j].strip() == "```":
                                k = j + 1
                                plines = []
                                while k < len(lines) and lines[k].strip() != "```":
                                    plines.append(lines[k])
                                    k += 1
                                if plines:
                                    prompt_text = "\n".join(plines).strip()
                            break

                    # Also try looking backward
                    if not prompt_text:
                        for j in range(i - 1, max(0, i - 40), -1):
                            if lines[j].strip() == "```":
                                k = j - 1
                                plines = []
                                while k >= 0 and not lines[k].strip().startswith("```"):
                                    plines.insert(0, lines[k])
                                    k -= 1
                                if plines:
                                    prompt_text = "\n".join(plines).strip()
                                break

                    if prompt_text:
                        recovered[folder] = {
                            "text": prompt_text,
                            "heading": heading,
                            "source": f"git:{commit[:7]}:{rf}",
                        }

    # Apply recovered prompts
    count = 0
    for folder, info in recovered.items():
        if folder in folder_map:
            idx, case = folder_map[folder]
            case["text"] = info["text"]
            if info.get("heading"):
                title_match = re.search(r'\[([^\]]+)\]', info["heading"])
                if title_match:
                    case["title"] = title_match.group(1)[:200]
            case["source"] = info["source"]
            count += 1
            print(f"    Recovered: {folder} ({len(info['text'])} chars)")

    elapsed = _time.time() - start_time
    print(f"    Git history scan done in {elapsed:.1f}s")
    return count


def _download_readme_from_github(filename="README.md"):
    """Download a README file from GitHub. Returns content string or None."""
    url = f"{GITHUB_RAW_BASE}/{filename}"
    try:
        print(f"  Downloading {url} ...")
        payload = read_url_with_retry(
            url,
            headers={"User-Agent": "ComfyUI-GPTImage2Prompt/1.0"},
            timeout=30,
        )
        content = payload.decode("utf-8")
        if "### Case" in content:
            return content
        print(f"  Downloaded but no cases found in {filename}")
        return None
    except Exception as e:
        print(f"  Download failed: {e}")
        return None


def _is_case_readme(filepath):
    """Check if a README file contains case definitions (### Case N:)."""
    try:
        with open(str(filepath), "r", encoding="utf-8") as f:
            # Read entire file to check (README may have cases far down)
            content = f.read()
        # Must contain actual ### Case N: pattern
        return bool(re.search(r'###\s*Case\s+\d+:', content))
    except Exception:
        return False


def _download_image_from_github(image_rel_path, dst_path):
    """Download an image from GitHub raw when not available locally.
    image_rel_path: e.g. 'images/portrait_case1/output.jpg'
    dst_path: absolute path to save the image
    Returns True on success.
    """
    url = f"{GITHUB_RAW_BASE}/{image_rel_path}"
    try:
        data = read_url_with_retry(
            url,
            headers={"User-Agent": "ComfyUI-GPTImage2Prompt/1.0"},
            timeout=30,
        )
        if len(data) < 100:  # Too small, probably an error page
            return False
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def main():
    print(f"[Config] NODE_DIR = {NODE_DIR}")
    print(f"[Config] SRC_IMAGES_DIR = {SRC_IMAGES_DIR} (exists={os.path.isdir(SRC_IMAGES_DIR)})")
    print(f"[Config] LOCAL_IMAGES_DIR = {LOCAL_IMAGES_DIR}")

    # Load existing data for safety comparison
    existing_presets = []
    if os.path.isfile(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                existing_presets = json.load(f)
        except Exception:
            pass

    # ========== Stage 1: Download & parse latest README from GitHub ==========
    readme_contents = []  # List of (source_name, content_string)
    readme_files = []     # List of Path objects (local)

    # Always download from GitHub to get the latest version
    print("[Stage 1] Downloading latest README from GitHub...")
    readme_names = ["README.md", "README_zh-CN.md", "README_de.md"]
    for rname in readme_names:
        content = _download_readme_from_github(rname)
        if content:
            readme_contents.append((rname, content))
            break  # One good README is enough

    # Also check local README in NODE_DIR (may have more cases)
    for search_dir in [NODE_DIR]:
        main_readme = search_dir / "README.md"
        if os.path.isfile(str(main_readme)) and _is_case_readme(str(main_readme)):
            readme_files.append(main_readme)
            break

    print(f"  Parsing {len(readme_files) + len(readme_contents)} README sources...")

    all_cases = []
    existing_image_paths = set()

    for readme_path in readme_files:
        cases = parse_single_readme(readme_path, existing_image_paths)
        if cases:
            print(f"  {readme_path.name}: {len(cases)} new cases")
        all_cases.extend(cases)

    for source_name, content in readme_contents:
        cases = parse_single_readme(content, existing_image_paths)
        if cases:
            print(f"  {source_name} (downloaded): {len(cases)} new cases")
        all_cases.extend(cases)

    readme_count = len(all_cases)
    print(f"  README total: {readme_count} cases")

    # ========== Stage 2: Scan images/ directory for uncovered folders ==========
    print(f"\n[Stage 2] Scanning images/ directory for uncovered folders...")
    image_only_cases = scan_images_directory(existing_image_paths)
    if image_only_cases:
        print(f"  Found {len(image_only_cases)} additional image folders (no prompt in README)")
        all_cases.extend(image_only_cases)
    else:
        print(f"  All image folders covered by README parsing")

    # ========== Stage 3: Recover prompts from git history ==========
    print(f"\n[Stage 3] Recovering prompts from git history...")
    empty_cases = [(i, c) for i, c in enumerate(all_cases) if not c["text"].strip()]
    if empty_cases:
        recovered = _recover_from_git_history(empty_cases)
        print(f"  Recovered {recovered} prompts from git history")

    # ========== Sort & deduplicate ==========
    all_cases.sort(key=lambda c: (c["category"], c["case_num"]))

    seen_ids = set()
    for c in all_cases:
        base_id = c["id"]
        if base_id in seen_ids:
            suffix = 1
            while f"{base_id}_{suffix}" in seen_ids:
                suffix += 1
            c["id"] = f"{base_id}_{suffix}"
        seen_ids.add(c["id"])

    # ========== Stats ==========
    cats = {}
    for c in all_cases:
        cat = c["category"]
        cats[cat] = cats.get(cat, 0) + 1

    with_prompt = sum(1 for c in all_cases if c["text"].strip())
    image_only = sum(1 for c in all_cases if not c["text"].strip())

    print(f"\n=== SUMMARY ===")
    print(f"Total entries: {len(all_cases)}")
    print(f"  With prompt + image: {with_prompt}")
    print(f"  Image only (no prompt): {image_only}")
    print(f"By category:")
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")

    # Verify coverage against source images/ directory
    if os.path.isdir(SRC_IMAGES_DIR):
        all_img_folders = set(f for f in os.listdir(SRC_IMAGES_DIR)
                             if os.path.isdir(os.path.join(SRC_IMAGES_DIR, f)))
        covered_folders = set()
        for c in all_cases:
            parts = c["image_path"].split("/")
            if len(parts) >= 2:
                covered_folders.add(parts[1])

        uncovered = all_img_folders - covered_folders
        print(f"\nSource image folders: {len(all_img_folders)}")
        print(f"Covered: {len(covered_folders)}")
        if uncovered:
            print(f"WARNING: {len(uncovered)} folders still uncovered!")
            for f in sorted(list(uncovered)[:20]):
                print(f"  {f}")
        else:
            print(f"All {len(all_img_folders)} image folders covered!")
    else:
        print(f"\n[Info] SRC_IMAGES_DIR not found, skipping coverage verification.")

    # ========== Incremental Merge with existing data ==========
    # Strategy: keep all existing entries, add new ones, update text if GitHub has better data
    existing_by_id = {p["id"]: p for p in existing_presets}
    new_added = 0
    text_updated = 0

    final_entries = []
    processed_ids = set()

    # First: process all newly discovered cases
    for c in all_cases:
        cid = c["id"]
        if cid in processed_ids:
            continue
        processed_ids.add(cid)

        old_entry = existing_by_id.get(cid)
        if old_entry:
            # Entry exists - merge: keep old, update text if new has better data
            merged = dict(old_entry)
            if c.get("text", "").strip() and not old_entry.get("text", "").strip():
                merged["text"] = c["text"]
                text_updated += 1
            final_entries.append(merged)
        else:
            # New entry from GitHub
            final_entries.append(c)
            new_added += 1

    # Second: keep existing entries not covered by new scan (shouldn't lose any)
    for p in existing_presets:
        if p["id"] not in processed_ids:
            final_entries.append(p)
            processed_ids.add(p["id"])

    print(f"\n[Merge] Incremental update: {new_added} new entries added, {text_updated} texts updated")
    print(f"  Total after merge: {len(final_entries)} entries")

    all_cases = final_entries

    # ========== Safety Check ==========
    old_total = len(existing_presets)
    new_total = len(all_cases)
    if old_total > 0 and new_total == 0:
        print(f"\n[SAFETY] Merge produced 0 entries but existing has {old_total}. NOT overwriting!")
        return
    if old_total > 50 and new_total < old_total * 0.5:
        print(f"\n[SAFETY] New count ({new_total}) is less than 50% of old ({old_total}). NOT overwriting!")
        import sys
        if "--force" not in sys.argv:
            return

    # ========== Stage 4: Copy images to node data/images/ directory ==========
    print(f"\n[Stage 4] Copying images to {LOCAL_IMAGES_DIR}...")
    os.makedirs(LOCAL_IMAGES_DIR, exist_ok=True)
    copied = 0
    skipped = 0
    downloaded = 0
    download_failed = 0
    for c in all_cases:
        # Skip opennana entries (they manage their own images)
        if c.get("id", "").startswith("opennana_"):
            img_rel = c.get("image_path", "")
            if img_rel:
                dst_check = os.path.join(LOCAL_IMAGES_DIR,
                    os.sep.join(img_rel.replace("/", os.sep).split(os.sep)[1:]) if os.sep in img_rel.replace("/", os.sep) else img_rel)
                if os.path.isfile(dst_check):
                    skipped += 1
                    c["image_exists"] = True
                    continue
            continue

        img_rel = c["image_path"]  # e.g. "images/portrait_case1/output.jpg"
        img_parts = img_rel.replace("/", os.sep).split(os.sep)  # ["images", "portrait_case1", "output.jpg"]
        # Sub-path within images/ dir
        sub_path = os.sep.join(img_parts[1:]) if len(img_parts) > 1 else img_parts[0]

        # Try multiple source locations (NODE_DIR only)
        src_path = None
        candidates = [
            os.path.join(SRC_IMAGES_DIR, sub_path),
            os.path.join(str(NODE_DIR), img_rel.replace("/", os.sep)),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                src_path = candidate
                break

        dst_path = os.path.join(LOCAL_IMAGES_DIR, sub_path)
        if src_path:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            if os.path.isfile(dst_path) and os.path.getsize(dst_path) == os.path.getsize(src_path):
                skipped += 1
            else:
                shutil.copy2(src_path, dst_path)
                copied += 1
            c["image_exists"] = True
        else:
            # Check if already in destination
            if os.path.isfile(dst_path):
                skipped += 1
                c["image_exists"] = True
            else:
                # Download from GitHub as last resort
                if _download_image_from_github(img_rel, dst_path):
                    downloaded += 1
                    c["image_exists"] = True
                else:
                    download_failed += 1
                    c["image_exists"] = False
    msg_parts = [f"Copied {copied}"]
    if downloaded:
        msg_parts.append(f"downloaded {downloaded} from GitHub")
    if download_failed:
        msg_parts.append(f"{download_failed} download failed")
    msg_parts.append(f"skipped {skipped} (already up to date)")
    print(f"  {', '.join(msg_parts)}")

    # ========== Save ==========
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {OUTPUT_JSON}")
    print(f"Node directory is now self-contained. Images at: {LOCAL_IMAGES_DIR}")


if __name__ == "__main__":
    main()
