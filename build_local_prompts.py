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

NODE_DIR = Path(__file__).resolve().parent            # comfyui-gpt-image2-prompt/
REPO_ROOT = NODE_DIR.parent                          # parent directory (may or may not be repo)

# Source images: prefer NODE_DIR/images/ (self-contained install),
# fallback to REPO_ROOT/images/ (dev/repo structure)
# Use os.path.isdir for reliable Windows path checking
_SRC_IN_NODE = str(NODE_DIR / "images")
_SRC_IN_REPO = str(REPO_ROOT / "images")
if os.path.isdir(_SRC_IN_NODE):
    SRC_IMAGES_DIR = _SRC_IN_NODE
elif os.path.isdir(_SRC_IN_REPO):
    SRC_IMAGES_DIR = _SRC_IN_REPO
else:
    SRC_IMAGES_DIR = _SRC_IN_NODE  # Will fail with clear error later

LOCAL_IMAGES_DIR = str(NODE_DIR / "data" / "images")  # Destination inside node dir
OUTPUT_JSON = str(NODE_DIR / "data" / "local_prompts.json")

# GitHub raw base URL for downloading README files
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/EvoLinkAI/awesome-gpt-image-2-prompts/main"

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

            # Accept case if we have image (prompt may be empty)
            if image_path and image_path not in existing_image_paths:
                # Verify image exists locally
                img_exists = _check_image_exists(image_path)
                if img_exists:
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
                        "image_exists": True,
                        "source": source_name,
                    })
                    existing_image_paths.add(image_path)

        i += 1

    return cases


def _check_image_exists(image_rel_path):
    """Check if an image exists in any known location."""
    # Try SRC_IMAGES_DIR parent (e.g. REPO_ROOT/images/xxx or NODE_DIR/images/xxx)
    candidates = [
        os.path.join(SRC_IMAGES_DIR, os.sep.join(image_rel_path.split("/")[1:])),  # images/xxx -> SRC/xxx
        os.path.join(str(NODE_DIR), image_rel_path.replace("/", os.sep)),
        os.path.join(str(REPO_ROOT), image_rel_path.replace("/", os.sep)),
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


def scan_images_directory(existing_image_paths):
    """Scan images/ directory for any folders not yet covered.
    Creates entries for uncovered folders (image-only, no prompt text from README).
    Automatically skips folders that are duplicates of already-covered folders.
    """
    if not os.path.isdir(SRC_IMAGES_DIR):
        print(f"  [Warning] SRC_IMAGES_DIR does not exist: {SRC_IMAGES_DIR}")
        return []

    cases = []
    covered_folders = set()
    for img_path in existing_image_paths:
        parts = img_path.split("/")
        if len(parts) >= 2:
            covered_folders.add(parts[1])

    # Build MD5 map to detect duplicate image folders
    md5_map = _build_md5_map()
    # Build reverse map: folder -> hash
    folder_hash = {}
    for h, folders in md5_map.items():
        for f in folders:
            folder_hash[f] = h

    for folder_name in sorted(os.listdir(SRC_IMAGES_DIR)):
        folder_path = os.path.join(SRC_IMAGES_DIR, folder_name)
        if not os.path.isdir(folder_path) or folder_name in covered_folders:
            continue

        # Skip non-case folders (like 'logo.png' file or special dirs)
        if folder_name.startswith("."):
            continue

        # Find an image file in this folder
        img_file = _find_best_image(folder_path)
        if not img_file:
            continue

        # Skip if this folder's image is a duplicate of an already-covered folder
        h = folder_hash.get(folder_name)
        if h:
            same_hash_folders = md5_map.get(h, [])
            if any(f in covered_folders for f in same_hash_folders):
                continue

        image_path = f"images/{folder_name}/{img_file}"
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
            "image_exists": True,
            "source": "images_directory",
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

    # Determine git working directory (could be NODE_DIR or REPO_ROOT)
    git_cwd = None
    for candidate in [NODE_DIR, REPO_ROOT]:
        try:
            r = subprocess.run(["git", "rev-parse", "--git-dir"],
                             cwd=str(candidate), capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                git_cwd = str(candidate)
                break
        except Exception:
            continue
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
    import urllib.request
    url = f"{GITHUB_RAW_BASE}/{filename}"
    try:
        print(f"  Downloading {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-GPTImage2Prompt/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
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

    # ========== Stage 1: Parse all README files ==========
    readme_files = []  # List of Path objects
    readme_contents = []  # List of (source_name, content_string) for downloaded READMEs

    # Look for case READMEs locally (NODE_DIR first, then REPO_ROOT)
    for search_dir in [NODE_DIR, REPO_ROOT]:
        main_readme = search_dir / "README.md"
        if os.path.isfile(str(main_readme)) and _is_case_readme(str(main_readme)):
            if main_readme not in readme_files:
                readme_files.append(main_readme)
        for f in sorted(Path(str(search_dir)).glob("README_*.md")):
            if os.path.isfile(str(f)) and _is_case_readme(str(f)):
                if f not in readme_files:
                    readme_files.append(f)

    # If no case READMEs found locally, download from GitHub
    if not readme_files and not readme_contents:
        print("  No local case README found, downloading from GitHub...")
        readme_names = ["README.md", "README_zh-CN.md", "README_de.md"]
        for rname in readme_names:
            content = _download_readme_from_github(rname)
            if content:
                readme_contents.append((rname, content))
                break  # One good README is enough

    print(f"[Stage 1] Parsing {len(readme_files) + len(readme_contents)} README files...")

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

    # If README parsing yielded 0 cases, try downloading from GitHub as fallback
    if readme_count == 0 and not readme_contents:
        print("  No cases parsed locally, trying GitHub download as fallback...")
        readme_names_dl = ["README.md", "README_zh-CN.md", "README_de.md"]
        for rname in readme_names_dl:
            content = _download_readme_from_github(rname)
            if content:
                cases = parse_single_readme(content, existing_image_paths)
                if cases:
                    print(f"  {rname} (downloaded): {len(cases)} new cases")
                    all_cases.extend(cases)
                    break
        if all_cases:
            print(f"  After GitHub fallback: {len(all_cases)} cases")

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

    # ========== Merge opennana entries from existing data ==========
    # Preserve opennana_* entries that were added by fetch_opennana.py
    existing_opennana = [p for p in existing_presets if p.get("id", "").startswith("opennana_")]
    new_ids = {c["id"] for c in all_cases}
    merged_opennana = [p for p in existing_opennana if p["id"] not in new_ids]
    if merged_opennana:
        print(f"\n[Merge] Preserving {len(merged_opennana)} opennana entries from existing data")
        all_cases.extend(merged_opennana)

    # ========== Safety Check ==========
    # Count only non-opennana, non-custom presets for safety comparison
    old_preset_count = len([p for p in existing_presets
                           if not p.get("id", "").startswith("custom_")
                           and not p.get("id", "").startswith("opennana_")])
    new_readme_count = len([c for c in all_cases
                           if not c.get("id", "").startswith("opennana_")])
    if old_preset_count > 0 and new_readme_count == 0:
        print(f"\n[SAFETY] Rebuild produced 0 README entries but existing has {old_preset_count}. NOT overwriting!")
        print(f"  This usually means README source was not found. Check paths and network.")
        return
    if old_preset_count > 50 and new_readme_count < old_preset_count * 0.5:
        print(f"\n[SAFETY] New count ({new_readme_count}) is less than 50% of old ({old_preset_count}). NOT overwriting!")
        print(f"  Pass --force to override this safety check.")
        import sys
        if "--force" not in sys.argv:
            return

    # ========== Stage 4: Copy images to node data/images/ directory ==========
    print(f"\n[Stage 4] Copying images to {LOCAL_IMAGES_DIR}...")
    os.makedirs(LOCAL_IMAGES_DIR, exist_ok=True)
    copied = 0
    skipped = 0
    for c in all_cases:
        img_rel = c["image_path"]  # e.g. "images/portrait_case1/output.jpg"
        img_parts = img_rel.replace("/", os.sep).split(os.sep)  # ["images", "portrait_case1", "output.jpg"]
        # Sub-path within images/ dir
        sub_path = os.sep.join(img_parts[1:]) if len(img_parts) > 1 else img_parts[0]

        # Try multiple source locations
        src_path = None
        candidates = [
            os.path.join(SRC_IMAGES_DIR, sub_path),
            os.path.join(str(NODE_DIR), img_rel.replace("/", os.sep)),
            os.path.join(str(REPO_ROOT), img_rel.replace("/", os.sep)),
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
                c["image_exists"] = False
    print(f"  Copied {copied} images, skipped {skipped} (already up to date)")

    # ========== Save ==========
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {OUTPUT_JSON}")
    print(f"Node directory is now self-contained. Images at: {LOCAL_IMAGES_DIR}")


if __name__ == "__main__":
    main()
