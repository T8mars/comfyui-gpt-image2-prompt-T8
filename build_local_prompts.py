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

NODE_DIR = Path(__file__).parent                     # comfyui-gpt-image2-prompt/
REPO_ROOT = NODE_DIR.parent                          # awesome-gpt-image-2-prompts/  (source)
SRC_IMAGES_DIR = REPO_ROOT / "images"                 # Source images in repo root
LOCAL_IMAGES_DIR = NODE_DIR / "data" / "images"       # Destination inside node dir
OUTPUT_JSON = NODE_DIR / "data" / "local_prompts.json"

# Section keyword mapping (works across languages)
SECTION_KEYWORDS = {
    "portrait": ["portrait", "photo", "retrato", "portr", "ritratt"],
    "poster": ["poster", "illustration", "cartel", "affiche", "plakat"],
    "character": ["character", "personaje", "personnage", "karakter", "charakt"],
    "ui": ["ui", "social media", "mockup", "interfaz", "maquette"],
    "comparison": ["comparison", "community", "comparaci", "comparais", "vergleich"],
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
    """
    content = readme_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    cases = []
    current_section = "other"
    i = 0

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
            j = i + 1
            while j < len(lines) and j < i + 50:
                # Find image - match HTML src="./images/..." AND Markdown ![...](images/...)
                if not image_path:
                    # HTML: <img src="./images/..." or src="images/..."
                    img_match = re.search(r'src="\.?/?\s*(images/[^"]+)"', lines[j])
                    if img_match:
                        image_path = img_match.group(1)
                    else:
                        # Markdown: ![alt text](./images/...) or ![alt](images/...)
                        md_match = re.search(r'!\[[^\]]*\]\(\.?/?\s*(images/[^)]+)\)', lines[j])
                        if md_match:
                            image_path = md_match.group(1)

                # Find prompt code block (``` after **Prompt** section)
                if lines[j].strip() == "```" and j > i + 2:
                    k = j + 1
                    prompt_lines = []
                    while k < len(lines):
                        if lines[k].strip() == "```":
                            break
                        prompt_lines.append(lines[k])
                        k += 1
                    if prompt_lines:
                        prompt_text = "\n".join(prompt_lines).strip()
                    break
                j += 1

            # Only add if we have both image and prompt, and image is not a duplicate
            if image_path and prompt_text and image_path not in existing_image_paths:
                full_img_path = REPO_ROOT / image_path
                if full_img_path.exists():
                    # Infer category from image folder name if section is generic
                    folder_name = image_path.split("/")[1] if "/" in image_path else ""
                    if current_section == "other" and folder_name:
                        for prefix in ["portrait", "poster", "character", "ui", "comparison"]:
                            if folder_name.startswith(prefix + "_"):
                                current_section = prefix
                                break

                    cases.append({
                        "id": f"{current_section}_case{case_num}",
                        "category": current_section,
                        "case_num": int(case_num),
                        "title": title[:200],
                        "author": author,
                        "text": prompt_text,
                        "image_path": image_path,
                        "image_exists": True,
                        "source": readme_path.name,
                    })
                    existing_image_paths.add(image_path)

        i += 1

    return cases


def _infer_category_from_folder(folder_name):
    """Infer category from folder name prefix like 'portrait_case1'."""
    for prefix in ["portrait", "poster", "character", "ui", "comparison"]:
        if folder_name.startswith(prefix + "_"):
            return prefix
    return "other"


def _find_best_image(folder_path):
    """Find the best image file in a folder (prefer output.jpg)."""
    folder = Path(folder_path)
    # Prefer output.jpg, then output*.jpg, then any image
    for pattern in ["output.jpg", "output*.jpg", "output*.png", "*.jpg", "*.png"]:
        matches = list(folder.glob(pattern))
        if matches:
            return matches[0].name
    return ""


def _build_md5_map():
    """Build MD5 hash map for all output.jpg files in source images/ directory."""
    import hashlib
    md5_map = {}  # hash -> list of folder names
    if not SRC_IMAGES_DIR.exists():
        return md5_map
    for folder_name in os.listdir(SRC_IMAGES_DIR):
        img = SRC_IMAGES_DIR / folder_name / "output.jpg"
        if img.is_file():
            h = hashlib.md5(img.read_bytes()).hexdigest()
            md5_map.setdefault(h, []).append(folder_name)
    return md5_map


def scan_images_directory(existing_image_paths):
    """Scan images/ directory for any folders not yet covered.
    Creates entries for uncovered folders (image-only, no prompt text from README).
    Automatically skips folders that are duplicates of already-covered folders.
    """
    if not SRC_IMAGES_DIR.exists():
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
        folder_path = SRC_IMAGES_DIR / folder_name
        if not folder_path.is_dir() or folder_name in covered_folders:
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
                print(f"    Skipping {folder_name} (duplicate of {[f for f in same_hash_folders if f in covered_folders]})")
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

    # Get commits that modified README files
    historical_commits = []
    try:
        r = subprocess.run(["git", "log", "--all", "--oneline", "--format=%H", "--", "README.md"],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15)
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
                                 cwd=str(REPO_ROOT), capture_output=True, timeout=10)
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


def main():
    # ========== Stage 1: Parse all README files ==========
    readme_files = []
    main_readme = REPO_ROOT / "README.md"
    if main_readme.exists():
        readme_files.append(main_readme)
    for f in sorted(REPO_ROOT.glob("README_*.md")):
        readme_files.append(f)

    print(f"[Stage 1] Parsing {len(readme_files)} README files...")

    all_cases = []
    existing_image_paths = set()

    for readme_path in readme_files:
        cases = parse_single_readme(readme_path, existing_image_paths)
        if cases:
            print(f"  {readme_path.name}: {len(cases)} new cases")
        all_cases.extend(cases)

    readme_count = len(all_cases)
    print(f"  README total: {readme_count} cases with prompt + image")

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
    all_img_folders = set(f for f in os.listdir(SRC_IMAGES_DIR) if (SRC_IMAGES_DIR / f).is_dir())
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
        for f in sorted(uncovered):
            print(f"  {f}")
    else:
        print(f"All {len(all_img_folders)} image folders covered!")

    # ========== Stage 4: Copy images to node data/images/ directory ==========
    print(f"\n[Stage 4] Copying images to {LOCAL_IMAGES_DIR}...")
    os.makedirs(LOCAL_IMAGES_DIR, exist_ok=True)
    copied = 0
    skipped = 0
    for c in all_cases:
        img_rel = c["image_path"]  # e.g. "images/portrait_case1/output.jpg"
        src_path = REPO_ROOT / img_rel
        dst_path = NODE_DIR / "data" / img_rel  # -> data/images/portrait_case1/output.jpg
        if src_path.is_file():
            os.makedirs(dst_path.parent, exist_ok=True)
            if dst_path.exists() and dst_path.stat().st_size == src_path.stat().st_size:
                skipped += 1
            else:
                shutil.copy2(str(src_path), str(dst_path))
                copied += 1
            c["image_exists"] = True
        else:
            c["image_exists"] = False
    print(f"  Copied {copied} images, skipped {skipped} (already up to date)")

    # ========== Save ==========
    os.makedirs(OUTPUT_JSON.parent, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {OUTPUT_JSON}")
    print(f"Node directory is now self-contained. Images at: {LOCAL_IMAGES_DIR}")


if __name__ == "__main__":
    main()
