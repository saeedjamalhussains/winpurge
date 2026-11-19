"""Large Files: big personal files in Desktop, Documents, Downloads, Videos,
Music and Pictures (plus folders you add), downloaded AI models, and
byte-for-byte duplicates. These are your files, so nothing here is ever
"Safe": they are never part of Clean Safe Items or a scheduled clean.

Skipped: hidden and system folders, project/dependency folders (Dev Tools
handles those), links and junctions, cloud-only files (opening them would
download them), and OneDrive/Dropbox folders (deleting there deletes from
every device)."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from .caches import PROJECT_JUNK
from .common import CHECK, Item, folder_size, is_link_or_junction
from .system import known_folder

MB = 1024 * 1024
USER_FOLDERS = ("Desktop", "Documents", "Downloads", "Videos", "Music", "Pictures")

# Cloud placeholders: reading them makes OneDrive download the file.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

KINDS = {
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".flv", ".ts"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".aiff", ".opus"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".raw", ".cr2", ".nef",
               ".arw", ".dng", ".psd", ".webp"},
    "PDFs": {".pdf"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zst", ".cab"},
    "Documents": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".csv", ".txt",
                  ".epub", ".key", ".pages"},
    "Installers": {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle"},
    "Disk images and VMs": {".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2", ".wim", ".esd"},
    "AI models": {".gguf", ".safetensors", ".ggml", ".pt", ".pth", ".ckpt", ".onnx"},
}
UNFINISHED = {".crdownload", ".part", ".partial", ".download", ".opdownload", ".!ut", ".!qb", ".tmp"}
SKIP_DIRS = {"node_modules", "$recycle.bin", "system volume information", "appdata", "windowsapps",
             "onedrive", "dropbox", "google drive", "icloud drive", "icloudrive"} | set(PROJECT_JUNK)


def kind_of(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in UNFINISHED:
        return "Unfinished downloads"
    for kind, exts in KINDS.items():
        if ext in exts:
            return kind
    return "Other"


def label_of(name: str, kind: str, folder: str) -> tuple[str, str]:
    """(tag, explanation) for files that carry one."""
    ext = os.path.splitext(name)[1].lower()
    if kind == "Unfinished downloads":
        return "Unfinished download", "A download that never finished. The browser can't resume it once it's closed."
    if ext in (".iso", ".img", ".wim", ".esd"):
        return "Disk image", "An installer or disk image. Only needed to set up Windows, a PC or a virtual machine."
    if ext in (".vhd", ".vhdx", ".vmdk", ".vdi", ".qcow2"):
        return "Virtual machine", ("A virtual machine's disk. If its app is still installed, remove the VM in that app, "
                                   "which keeps its own list.")
    if kind == "Installers" and os.path.basename(folder).lower() == "downloads":
        return "Installer", "A setup file you downloaded. Once the app is installed you no longer need it."
    return "", ""


def _cloud_roots(env) -> set[str]:
    roots = set()
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if env.get(var):
            roots.add(os.path.normcase(os.path.normpath(env[var])))
    return roots


def default_roots(env=None) -> list[str]:
    env = os.environ if env is None else env
    out = []
    for name in USER_FOLDERS:
        p = known_folder(name, env)
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    return out


def scan_large_files(roots: list[str], min_size: int = 50 * MB, env=None, max_files: int = 20000) -> list[Item]:
    env = os.environ if env is None else env
    cloud = _cloud_roots(env)
    items, seen = [], set()
    for root in roots:
        source = os.path.basename(os.path.normpath(root)) or root
        stack = [root]
        while stack and len(items) < max_files:
            folder = stack.pop()
            key = os.path.normcase(os.path.normpath(folder))
            if key in seen or any(key == c or key.startswith(c + os.sep) for c in cloud):
                continue
            seen.add(key)
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            if any(e.name in (".dropbox", ".dropbox.cache") for e in entries):
                continue   # a Dropbox folder: deleting here deletes everywhere
            for e in entries:
                if is_link_or_junction(e) or e.name.startswith(("." , "~$")):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                if stat.S_ISDIR(st.st_mode):
                    if e.name.lower() not in SKIP_DIRS and not attrs & 0x4:  # 0x4 = system
                        stack.append(e.path)
                    continue
                if st.st_size < min_size or attrs & CLOUD_ONLY:
                    continue
                kind = kind_of(e.name)
                tag, note = label_of(e.name, kind, folder)
                items.append(Item(
                    path=e.path, label=e.name, category=kind, level=CHECK, size=st.st_size, note=note,
                    tab="large", mtime=st.st_mtime,
                    extra={"source": source, "folder": folder, "tag": tag,
                           "atime": max(st.st_atime, st.st_mtime)}))
    return items


# ---------------------------------------------------------------- AI models

def _ollama_models(env) -> list[Item]:
    """One row per Ollama model. A model's size counts only the blobs no other
    model uses, so removing it frees exactly that much."""
    base = env.get("OLLAMA_MODELS") or (env.get("USERPROFILE") and os.path.join(env["USERPROFILE"], ".ollama", "models"))
    if not base or not os.path.isdir(os.path.join(base, "manifests")):
        return []
    blobs_dir = os.path.join(base, "blobs")
    models: list[tuple[str, str, set[str]]] = []
    for dirpath, _, files in os.walk(os.path.join(base, "manifests")):
        for f in files:
            mf = os.path.join(dirpath, f)
            try:
                data = json.loads(Path(mf).read_text("utf-8"))
            except (OSError, ValueError):
                continue
            digests = {l["digest"] for l in data.get("layers", []) + [data.get("config", {})] if l.get("digest")}
            rel = Path(os.path.relpath(mf, os.path.join(base, "manifests"))).parts
            name = f"{rel[-2]}:{rel[-1]}" if len(rel) >= 2 else rel[-1]
            models.append((name, mf, digests))
    use_count: dict[str, int] = {}
    for _, _, ds in models:
        for d in ds:
            use_count[d] = use_count.get(d, 0) + 1
    items = []
    for name, mf, ds in models:
        own = [os.path.join(blobs_dir, d.replace(":", "-")) for d in ds if use_count[d] == 1]
        own = [p for p in own if os.path.exists(p)]
        size = sum(os.path.getsize(p) for p in own)
        if size < MB:
            continue
        items.append(Item(path=mf, label=name, category="AI models", level=CHECK, size=size, tab="large",
                          mtime=os.path.getmtime(mf),
                          note="Downloaded by Ollama. Ollama will still list it until you run "
                               f"“ollama rm {name}”; download it again with “ollama pull {name}”.",
                          extra={"source": "Ollama", "paths": [mf] + own, "tag": "AI model"}))
    return items


def _model_folders(env) -> list[tuple[str, str, str]]:
    """(folder holding one model per subfolder, source name, note)."""
    home = env.get("USERPROFILE", "")
    local = env.get("LOCALAPPDATA", "")
    appdata = env.get("APPDATA", "")
    hf = env.get("HF_HUB_CACHE") or (env.get("HF_HOME") and os.path.join(env["HF_HOME"], "hub")) or \
        os.path.join(home, ".cache", "huggingface", "hub")
    return [
        (hf, "Hugging Face", "Downloaded through the Hugging Face Hub. It downloads again the next time a program asks for it."),
        (os.path.join(home, ".lmstudio", "models"), "LM Studio", "LM Studio may still list it as installed."),
        (os.path.join(home, ".cache", "lm-studio", "models"), "LM Studio", "LM Studio may still list it as installed."),
        (os.path.join(local, "nomic.ai", "GPT4All"), "GPT4All", ""),
        (os.path.join(appdata, "Jan", "data", "models"), "Jan", ""),
        (os.path.join(home, "jan", "models"), "Jan", ""),
        (os.path.join(home, ".cache", "whisper"), "Whisper", ""),
        (os.path.join(home, ".cache", "torch", "hub", "checkpoints"), "PyTorch Hub", ""),
    ]


def scan_ai_models(env=None) -> list[Item]:
    env = os.environ if env is None else env
    items = _ollama_models(env)
    for folder, source, note in _model_folders(env):
        if not folder or not os.path.isdir(folder):
            continue
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            if is_link_or_junction(e) or e.name.startswith("."):
                continue
            size = folder_size(e.path, limit_seconds=5) if e.is_dir(follow_symlinks=False) else e.stat().st_size
            if size < 100 * MB:
                continue
            name = e.name
            if name.startswith("models--"):
                name = name[8:].replace("--", "/")
            items.append(Item(path=e.path, label=name, category="AI models", level=CHECK, size=size, tab="large",
                              mtime=e.stat(follow_symlinks=False).st_mtime, note=note,
                              extra={"source": source, "tag": "AI model"}))
    return items


# ---------------------------------------------------------------- duplicates

def _hash(path: str, limit: int | None = None) -> str | None:
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as f:
            remaining = limit
            while True:
                chunk = f.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(items: list[Item]) -> list[list[Item]]:
    """Groups of byte-for-byte identical files: same size, then same first
    64 KB, then the same full content. Only real files (not model folders)."""
    by_size: dict[int, list[Item]] = {}
    for it in items:
        if it.category != "AI models" and os.path.isfile(it.path):
            by_size.setdefault(it.size, []).append(it)
    groups = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_head: dict[str, list[Item]] = {}
        for it in same_size:
            h = _hash(it.path, 64 * 1024)
            if h:
                by_head.setdefault(h, []).append(it)
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            by_full: dict[str, list[Item]] = {}
            for it in same_head:
                h = _hash(it.path)
                if h:
                    by_full.setdefault(h, []).append(it)
            groups += [g for g in by_full.values() if len(g) > 1]
    return groups


def suggest_keeper(group: list[Item]) -> Item:
    """Keep the oldest copy (usually the original); on a tie, the shortest path."""
    return min(group, key=lambda i: (i.mtime, len(i.path)))


def mark_duplicates(items: list[Item]) -> list[list[Item]]:
    groups = find_duplicates(items)
    for n, g in enumerate(groups, 1):
        keep = suggest_keeper(g)
        for it in g:
            it.extra["dup_group"] = n
            it.extra["dup_keep"] = it is keep
    return groups
