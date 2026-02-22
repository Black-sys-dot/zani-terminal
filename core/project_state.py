import os
import hashlib

CHUNK = 8192


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def scan_project(root: str, allowed_files: list[str]):
    """
    Returns:
        file_hashes: {rel_path: sha256}
        total_bytes: int
        file_sizes: {rel_path: size}
    """
    hashes = {}
    sizes = {}
    total = 0

    for rel in allowed_files:
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            continue

        size = os.path.getsize(full)
        digest = hash_file(full)

        hashes[rel] = digest
        sizes[rel] = size
        total += size

    return hashes, total, sizes


def diff_projects(old_hashes, new_hashes):
    added = []
    modified = []
    deleted = []

    for f in new_hashes:
        if f not in old_hashes:
            added.append(f)
        elif new_hashes[f] != old_hashes[f]:
            modified.append(f)

    for f in old_hashes:
        if f not in new_hashes:
            deleted.append(f)

    return added, modified, deleted


def compute_change_magnitude(added, modified, deleted, new_sizes, old_sizes, total_old_bytes):
    changed_bytes = 0

    for f in added:
        changed_bytes += new_sizes.get(f, 0)

    for f in modified:
        changed_bytes += new_sizes.get(f, 0)

    for f in deleted:
        changed_bytes += old_sizes.get(f, 0)

    percent = 0.0
    if total_old_bytes > 0:
        percent = (changed_bytes / total_old_bytes) * 100

    changed_tokens = changed_bytes // 4

    return changed_bytes, percent, changed_tokens
