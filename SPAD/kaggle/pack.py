"""Build the Kaggle dataset: code plus design captures, never held-out captures."""
import argparse
import json
from pathlib import Path
import shutil

SPAD = Path(__file__).resolve().parents[1]
# Only what the cloud run needs; package __init__ files keep python -m imports working.
CODE = ("spad/__init__.py", "spad/dataset/__init__.py", "spad/dataset/download.py",
        "spad/dataset/prepare.py", "spad/dataset/photons.py", "spad/core/__init__.py",
        "spad/core/model.py", "spad/core/stream_model.py", "spad/training/__init__.py",
        "spad/training/baselines.py", "spad/training/police.py", "spad/training/train_stream.py",
        "spad/evaluation/__init__.py",
        "spad/evaluation/bench_stream.py", "tests/__init__.py", "tests/test_device.py")
ALLOWED_SPLITS = {"train", "architecture", "validation"}


def build(data, out, user=None):
    metadata = json.loads((data/"processed/metadata.json").read_text())
    design = {c: {"split": v["split"], "selected_rays": v["selected_rays"]}
              for c, v in metadata["captures"].items() if v["split"] in ALLOWED_SPLITS}
    if out.exists():
        shutil.rmtree(out)
    (out/"code/kaggle").mkdir(parents=True)
    (out/"data/processed").mkdir(parents=True)
    (out/"data/asap7").mkdir(parents=True)
    for name in CODE:
        (out/"code"/name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SPAD/name, out/"code"/name)
    shutil.copy(SPAD/"kaggle/launch.py", out/"code/kaggle/launch.py")
    shutil.copy(SPAD/"kaggle/jobs.txt", out/"code/kaggle/jobs.txt")
    shutil.copy(data/"asap7/costs.json", out/"data/asap7/costs.json")
    for capture in design:
        for name in (f"{capture}.npz", f"labels_{capture}.npz"):
            shutil.copy(data/"processed"/name, out/"data/processed"/name)
    (out/"data/processed/metadata.json").write_text(json.dumps({**metadata, "captures": design}, indent=2)+"\n")
    if user:
        (out/"dataset-metadata.json").write_text(json.dumps({
            "title": "spad-stream-design", "id": f"{user}/spad-stream-design",
            "licenses": [{"name": "CC-BY-NC-SA-4.0"}]}, indent=2)+"\n")
    held_out = {c for c, v in metadata["captures"].items() if v["split"] not in ALLOWED_SPLITS}
    leaked = [p for p in (out/"data/processed").iterdir() if p.stem.removeprefix("labels_") in held_out]
    if leaked:
        raise RuntimeError(f"Held-out captures in bundle: {leaked}")
    # Depth captures by number, then Reconstruction views by name.
    return sorted(design, key=lambda c: (not c.isdigit(), int(c) if c.isdigit() else c))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=SPAD/"data")
    parser.add_argument("--out", type=Path, default=SPAD/"kaggle/dist/spad-stream-design")
    parser.add_argument("--kaggle-user", help="Adds dataset-metadata.json for the kaggle CLI")
    args = parser.parse_args()
    captures = build(args.data, args.out, args.kaggle_user)
    archive = shutil.make_archive(str(args.out), "zip", args.out)
    print(f"Captures {captures} -> {archive} ({Path(archive).stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
