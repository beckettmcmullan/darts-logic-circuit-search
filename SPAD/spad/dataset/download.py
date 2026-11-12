"""Download a pinned, bounded subset; never clone the full dataset or use an HF cache."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

from spad import ROOT
HF = "https://huggingface.co"
DATASET = "shuinb/SP-TransientBench"
ASAP = "The-OpenROAD-Project/asap7sc7p5t_28"
CAPTURES = {str(i) for i in range(1, 11)}
# Weights, routing and checkpoint selection each get their own captures.
# fresh_test (9-10) was never inspected during the pilot.
SPLITS = {"train": [1, 2, 3, 4], "architecture": [5], "validation": [6],
          "test": [7, 8], "fresh_test": [9, 10]}


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def usage(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def fetch(url, path, root, budget, expected=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is None or digest == expected:
            return digest
        raise ValueError(f"Existing file failed checksum: {path}")
    part = path.with_suffix(path.suffix + ".part")
    if part.exists():
        part.unlink()  # Only our incomplete download, never user data.
    available = budget - usage(root)
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as out:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                size += len(chunk)
                if size > available:
                    raise RuntimeError("Dataset storage budget would be exceeded")
                digest.update(chunk)
                out.write(chunk)
        if expected and digest.hexdigest() != expected:
            raise ValueError(f"Checksum mismatch: {path}")
        part.replace(path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    print(f"downloaded {path.relative_to(root)} ({size / 1e6:.1f} MB)", flush=True)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "data")
    parser.add_argument("--budget-bytes", type=int, default=1_200_000_000)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["budget_bytes"], manifest["splits"] = args.budget_bytes, SPLITS
    else:
        manifest = {
            "dataset": DATASET,
            "dataset_revision": get_json(f"{HF}/api/datasets/{DATASET}")["sha"],
            "asap7_revision": get_json(f"https://api.github.com/repos/{ASAP}/commits/main")["sha"],
            "budget_bytes": args.budget_bytes,
            "splits": SPLITS,
            "files": {},
        }
    rev = manifest["dataset_revision"]
    trees = {}
    for folder in ("DepthEstimate/Histogram", "DepthEstimate/gt"):
        trees[folder] = get_json(f"{HF}/api/datasets/{DATASET}/tree/{rev}/{folder}")
    wanted = []
    for folder, entries in trees.items():
        for item in entries:
            if Path(item["path"]).stem in CAPTURES:
                wanted.append((item["path"], item.get("lfs", {}).get("oid")))
    raw_size = sum(x["size"] for entries in trees.values() for x in entries
                   if Path(x["path"]).stem in CAPTURES)
    # Includes peak space for processed rays, metadata and library decompression.
    if raw_size + 140_000_000 > args.budget_bytes:
        raise RuntimeError("Selected raw data plus preprocessing reserve exceeds budget")
    for name in ("config/config.yaml", "config/final_extrinsic_sp_to_livox.txt",
                 "config/offset.txt", "config/IRF_global.csv", "README.md",
                 "codes/pointcloud_extract/raw2pc.py"):
        wanted.append((name, None))
    for name, checksum in wanted:
        url = f"{HF}/datasets/{DATASET}/resolve/{rev}/{urllib.parse.quote(name)}"
        digest = fetch(url, root / "raw" / name, root, args.budget_bytes, checksum)
        manifest["files"]["raw/" + name] = {"url": url, "sha256": digest}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    rev = manifest["asap7_revision"]
    entries = get_json(f"https://api.github.com/repos/{ASAP}/contents/LIB/NLDM?ref={rev}")
    for item in entries:
        if "RVT_TT" not in item["name"] or not any(
                "_" + kind + "_" in item["name"] for kind in ("SIMPLE", "INVBUF", "SEQ")):
            continue
        name = "asap7/" + item["name"]
        digest = fetch(item["download_url"], root / name, root, args.budget_bytes)
        manifest["files"][name] = {"url": item["download_url"], "sha256": digest}
    for name in ("LICENSE", "README.md"):
        url = f"https://raw.githubusercontent.com/{ASAP}/{rev}/{name}"
        digest = fetch(url, root / "asap7" / name, root, args.budget_bytes)
        manifest["files"]["asap7/" + name] = {"url": url, "sha256": digest}
    manifest["downloaded_bytes"] = usage(root)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Storage: {usage(root):,} / {args.budget_bytes:,} bytes", flush=True)


if __name__ == "__main__":
    main()
