# Constraints lab status

All six tracks finished on 2026-11-12. Nothing is running. Each track's full report is in
`constraints_lab/<track>/REPORT.md`; runs are in `runs/2026-11-11_constraints-lab/<track>/`.

| Track | Outcome | Form |
|---|---|---|
| `steadiness` | Adopt with changes | Hard limit at selection: offset spread across photon counts and background ≤ 1.0 bin on the paired validation grid. No weighted penalty |
| `tail` | Adopt with changes | Hard limit at selection: share of pixels off by more than 1 m ≤ start + 0.2 points. No capped loss |
| `valid` | Adopt | `valid_out = confidence >= 8`; hard limits at selection: false alarms ≤ 1%, detection ≥ 97% |
| `sensor` | Adopt with changes | Two hard limits at selection: pile-up offset shift at k = 4 ≤ 3 bins; within-3-bins drop under 2-bin jitter ≤ 3 points. No training on perturbed streams |
| `settle` | Do not adopt as a constraint | Report the error-versus-photons curve; optional selection check: within-3-bins at 16 photons no more than 3 points below the start |
| `flops` | Do not adopt | No state-bit cap, no flip-flop weight, no 3-bit counter. A 2x weight is the better tool if flip-flop count must fall |

Finding shared by the `flops`, `steadiness` and `settle` tracks: the design splits (train,
architecture) are a poor stand-in for validation. The area search's 5% accuracy budget on the
design splits does not bound validation error; only selection on validation does.

Nothing from the lab has been built into `spad/training/train_stream.py` yet.

Subagents could not write `REPORT.md` themselves in this setup: they handed the text back and the
main session saved it (the user approved this on 2026-11-11).
