"""Time gradient steps and hard-search evaluations on a device. Prints JSON."""
import argparse
import json
import time

import torch

from spad.dataset.photons import sample_photons
from spad.core.stream_model import (StreamConfig, StreamCore, pack_circuit, set_search_compile,
                                    simulate_population_packed)


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize()
    elif device.type == "mps":
        torch.mps.synchronize()


def timed(function, device, repeats):
    function()
    synchronize(device)
    started = time.perf_counter()
    for _ in range(repeats):
        function()
    synchronize(device)
    return (time.perf_counter() - started) / repeats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--budget", type=int, default=256, help="Photons per ray: the training maximum")
    parser.add_argument("--batches", type=int, nargs="+", default=[256, 1024, 4096, 8192])
    parser.add_argument("--populations", type=int, nargs="+", default=[64, 256, 1024])
    parser.add_argument("--compile", choices=("none", "default", "reduce-overhead"), default="none")
    parser.add_argument("--compile-search", choices=("none", "default", "reduce-overhead"), default="none")
    parser.add_argument("--skip-search", action="store_true", help="Only time the gradient step")
    parser.add_argument("--skip-gradient", action="store_true", help="Only time the search")
    parser.add_argument("--search-rays", type=int, default=2048)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    device = torch.device(args.device)
    config = StreamConfig()
    model = StreamCore(config).to(device).set_compile(None if args.compile == "none" else args.compile)
    set_search_compile(None if args.compile_search == "none" else args.compile_search)
    histograms = torch.randint(0, 40, (8192, 672), device=device)
    gradient = {}
    for batch in ([] if args.skip_gradient else args.batches):
        photons = sample_photons(histograms[:batch], args.budget)
        targets = torch.rand(batch, device=device)*200

        def step():
            model.zero_grad(set_to_none=True)
            torch.nn.functional.huber_loss(model(photons, temperature=.5, ste=True), targets).backward()
        seconds = timed(step, device, args.repeats)
        gradient[batch] = {"seconds_per_step": seconds, "rays_per_second": batch/seconds}
    search = {}
    inputs, codes = pack_circuit(model.circuit(), device)
    photons = sample_photons(histograms[:args.search_rays], args.budget)
    for population in ([] if args.skip_search else args.populations):
        stacked = inputs[None].repeat(population, 1, 1, 1), codes[None].repeat(population, 1, 1)
        seconds = timed(lambda: simulate_population_packed(config, *stacked, photons), device, args.repeats)
        search[population] = {"seconds_per_evaluation": seconds, "circuits_per_second": population/seconds}
    print(json.dumps({"device": str(device), "compile": args.compile, "compile_search": args.compile_search,
                      "budget": args.budget, "search_rays": args.search_rays,
                      "gradient": gradient, "hard_search": search}, indent=2))


if __name__ == "__main__":
    main()
