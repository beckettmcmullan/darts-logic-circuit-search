"""Check the tracing simulators against the shared ones, and time them."""
import json, time
import torch
from spad import ROOT
from spad.dataset.photons import load_rays
from spad.core.stream_model import StreamConfig, pack_circuit, simulate_stream, simulate_population_packed
from constraints_lab.settle.settle import full_streams, trace_stream, trace_population_packed, READOUTS

torch.set_num_threads(1)
circuit = json.loads((ROOT/"runs/2026-11-11_local-cpu_area-objective/final-design-tol5/circuit.json").read_text())
hist = load_rays(ROOT/"data", "validation")[0]
g = torch.Generator().manual_seed(0)
photons = full_streams(hist[:2048], generator=g)[0]
t = time.time(); tr = trace_stream(circuit, photons, READOUTS); print("trace 2048x256", time.time()-t)
for n in READOUTS:
    assert torch.equal(tr[n], simulate_stream(circuit, photons[:, :n])), n
config = StreamConfig(**circuit["config"])
i, c = pack_circuit(circuit)
t = time.time(); pk = trace_population_packed(config, i[None].repeat(4,1,1,1), c[None].repeat(4,1,1), photons, READOUTS); print("packed 4x2048x256", time.time()-t)
for k, n in enumerate(READOUTS):
    assert torch.equal(pk[k, 0].long(), tr[n]), n
print("ok, rays", len(hist))
