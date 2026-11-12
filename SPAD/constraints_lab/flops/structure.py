"""Structural liveness: which state bits, confidence flags and actions a circuit really uses.

Ignores signal activity (a structurally read signal counts even if constant), but follows
truth-table dependence: a gate input counts only if the table depends on it. The confidence
counter (and its inc/dec gates) counts only if a live gate reads one of its flags.
"""
from spad.core.stream_model import ACTIONS, StreamConfig, input_names
from spad.hardware.area_model import CONFIDENCE_FLAGS


def depends(table):
    t0, t1, t2, t3 = table
    return (t0 != t2) or (t1 != t3), (t0 != t1) or (t2 != t3)


def structure(circuit):
    c = StreamConfig(**circuit["config"])
    names = input_names(c)
    base = len(names)
    layers = circuit["layers"]
    width = c.width
    roots = {c.state_bits + ACTIONS.index(a) for a in ("replace", "up", "down")}
    counter, state_read = False, set()
    while True:
        live = [set() for _ in layers]
        live[-1] = set(roots) | ({c.state_bits + ACTIONS.index(a) for a in ("inc", "dec")} if counter else set()) | state_read
        read = set()
        for depth in range(len(layers) - 1, -1, -1):
            for g in sorted(live[depth]):
                (a, b), table = layers[depth]["inputs"][g], layers[depth]["truth_tables"][g]
                for src, used in zip((a, b), depends(table)):
                    if not used:
                        continue
                    if src < base:
                        read.add(names[src])
                    else:
                        live[depth - 1].add(src - base)
        new_counter = any(f in read for f in CONFIDENCE_FLAGS)
        # A state bit whose next value is constant 0 stays at its reset value: no flip-flop.
        new_state = {i for i in range(c.state_bits) if f"state{i}" in read and any(layers[-1]["truth_tables"][i])}
        if new_counter == counter and new_state == state_read:
            break
        counter, state_read = new_counter, new_state
    flags = [n for n in names if n in read and not n.startswith(("state", "const"))]
    return {"live_state_bits": sorted(state_read), "counter_live": counter,
            "confidence_flags_read": [f for f in CONFIDENCE_FLAGS if f in read], "flags_read": flags,
            "live_gates": sum(len(x) for x in live), "expected_flops": c.cand_bits + len(state_read) + c.conf_bits*counter}
