# SPAD: measuring distance one photon at a time

Can a neural network design a circuit that measures distance from single photons
without storing a histogram? This project searches for a circuit using real
single-photon sensor data to find task-driven insights from it.

A lidar pixel with a single-photon avalanche diode (SPAD) records when each
returning photon arrives, in time bins of 750 ps (11.2 cm of range, 672 bins in
all). Many photons are background light arriving at random times. The usual
method counts photons into a **histogram**, one counter per bin, and reads the
distance at the tallest pile. Each circuit here keeps one running distance
guess instead, and on every photon:

1. **A fixed comparator** (designed by hand) compares the photon's arrival bin
   with the guess and sets yes/no flags: is it within 1, 2, 4, 8 or 16 bins of
   the guess, is it later or earlier, and is the confidence count zero, at
   least 2, 4 or 8, or full?
2. **Learned logic gates** (3 layers of two-input gates; training picks each
   gate's inputs and truth table) read the flags and a few memory bits and pick
   the actions: replace the guess with this photon's bin, move it one step
   later or earlier, raise or lower the confidence count, and set the memory
   bits.
3. **Registers** keep the new guess, count and memory bits for the next photon.

For example, the area-optimized circuit's guess is bin 400 and a photon lands
in bin 410. The flags say "within 16, not within 8, later". Its gates always
answer a photon 5 to 16 bins after the guess with "one step later", so the guess
becomes 401. Photons more than 16 bins away are ignored as background.

## The two circuits

| | [Area-optimized](area-optimized/README.md) | [Accuracy-focused](accuracy-focused/README.md) | Histogram (for reference) |
|---|---|---|---|
| Goal during the search | small chip area | accuracy only | – |
| Step of the guess | 1 bin (11.2 cm) | down to 1/8 bin (1.4 cm) | 1 bin; a sub-bin fit reads between bins |
| Memory per pixel | 18 bits: 10-bit guess, 4-bit confidence, 4 memory bits | 66 bits (66 flip-flops, one bit each) | about 8,064 bits (672 counters) |
| Die area | 110 µm² | 281.0 µm² | – |
| Fastest clock | 682 ps (1.47 GHz) | 743 ps (1.35 GHz) | – |
| Mean error, 16-32 photons | 0.453 m | 0.167 m | 0.104 m |
| Mean error, 128-256 photons | 0.101 m | 0.047 m | 0.032 m |

Die area and clock come from routed layouts in ASAP7, a predictive 7 nm library
that no factory makes, so they are estimates.

Mean error is the average distance between the answer and the target. It comes
from validation run v4 on the design recordings (one of the four recording
sets: training, design, validation, held-out test), with 20 random photon
samples from every trusted ray. A ray is one pixel of one recording. It is
trusted if it recorded at least 1,024 photons and a sub-bin fit of its whole
recording lies within 3 bins of the reference distance; that fit is the target.
[`area-optimized/validation/`](area-optimized/validation/README.md) explains why.

**Which to pick:**

- **Area-optimized** when pixel area matters most: the smallest circuit, about
  450 times less memory than a histogram.
- **Accuracy-focused** when accuracy at low photon counts matters most: it moves
  the guess in steps of 1, 1/2, 1/4 or 1/8 bin and adds a coincidence gate,
  which blocks a jump to a far photon unless one of the last 4 photons arrived
  within 8 bins of it. It is 2.6 times the area and still behind the histogram
  fit at 16-32 photons.

## Shared setup

| Folder or file | Purpose |
|---|---|
| [`area-optimized/`](area-optimized/README.md) | The small circuit: training code, circuit, layout and validation |
| [`accuracy-focused/`](accuracy-focused/README.md) | The accurate circuit, laid out the same way |
| [`requirements.txt`](requirements.txt) | Python packages for both circuits |
| `data/` | The dataset, shared by both circuits (not in git) |

Run each circuit's commands from inside its own folder. Both folders' dataset
scripts write to the same `SPAD/data/`, so the dataset is fetched once, from
either folder:

```bash
cd SPAD/area-optimized
python -m neuralnetwork.dataset.download     # writes to SPAD/data/
```

The circuit READMEs list the remaining steps.

## Dataset licence

The photon data is
**[SP-TransientBench](https://huggingface.co/datasets/shuinb/SP-TransientBench)**,
real SPAD recordings of indoor and outdoor scenes, licensed CC BY-NC-SA 4.0. It
is not included in this repository; the download script fetches it (about 2.2 GB
after preparation).
