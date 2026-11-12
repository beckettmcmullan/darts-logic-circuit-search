"""Print the valid-bit table from roc.json files: best readout at 1% false alarms per background set."""
import json
import sys

KINDS = (("uniform",), ("residual",), ("residual_far",), ("uniform", "residual"), ("uniform", "residual_far"))


def best(rows, kinds, limit=.01):
    ok = [(x["detect"], k, max(x[f"fa_{c}"] for c in kinds), x.get("detect_and_correct"))
          for k, x in rows.items() if all(f"fa_{c}" in x for c in kinds) and max(x[f"fa_{c}"] for c in kinds) <= limit]
    return max(ok) if ok else None


for path in sys.argv[1:]:
    r = json.load(open(path))
    for name, e in r["circuits"].items():
        a, o = e["audit"], e["audit"]["overall"]
        offsets = [round(a[k]["median_signed_bins"], 1) for k in a if k.startswith("photons")]
        print(f"== {name}: MAE {o['mae_m']:.3f} median {o['median_m']:.3f} within3 {o['recall_3_bins']:.3f} "
              f"rmse {o['rmse_m']:.2f} offsets {offsets} shift {a['time_shift_test']['moves_with_photons_within_1_bin']:.3f} "
              f"synth {e.get('synthesized')}")
        for kinds in KINDS:
            b = best(e["valid"]["readouts"], kinds)
            rep = best(e["valid_repeat"]["readouts"], kinds) if all(
                f"fa_{c}" in next(iter(e["valid_repeat"]["readouts"].values())) for c in kinds) else "n/a"
            fmt = lambda x: "none <= 1%" if x is None else x if isinstance(x, str) else \
                f"{x[0]:.3f} ({x[1]}, FA {x[2]:.4f}" + (f", correct {x[3]:.3f})" if x[3] is not None else ")")
            print(f"   {'+'.join(kinds):24s} {fmt(b)}   repeat {fmt(rep)}")
