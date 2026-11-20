# darts-logic-circuit-search

Differentiable architecture search (DARTS) used to discover digital logic
circuits with PyTorch.

## The idea

A logic circuit is a set of gates and the wires between them. Choosing a gate
type or a wire is a discrete choice, so ordinary gradient descent cannot search
over it. DARTS removes the problem by making each choice soft during training.

- **Gates.** Every gate slot holds one score per candidate gate (AND, OR, XOR,
  and so on). A softmax turns the scores into weights. The slot outputs the
  weighted blend of all candidate gates. In the SPAD project each gate is a
  blend of 2-input truth tables instead.
- **Wiring.** Every gate input is a softmax-weighted blend of all signals it is
  allowed to read: the circuit inputs and earlier gates. A mask blocks later
  gates, so there are no loops.
- **Training.** The blended circuit is smooth, so the loss on a target truth
  table or dataset sends gradients to every score. An optimizer (Adam) updates
  them. A falling softmax temperature and random noise push choices toward a
  single option.
- **Hardening.** At the end each blend is replaced by its highest-weight option.
  The result is an ordinary circuit of discrete gates. It is then checked on its
  own, because a good soft circuit can become wrong when hardened.

## Repository map

| Folder | Contents |
|---|---|
| [`basics/`](basics/README.md) | The learning experiments, in order: `firstDARTS.py`, `DARTS2.py`, `DARTS3.py`, then gate-level searches for a [full adder](basics/full-adder-discovery/README.md) and a [1011 sequence detector](basics/sequence-detector/README.md). |
| [`SPAD/`](SPAD/README.md) | The main project: a learned circuit that measures distance from single-photon sensor data, taken through to an ASAP7 chip layout. |

Start with [`basics/README.md`](basics/README.md) to see how the idea builds up.
Read [`SPAD/README.md`](SPAD/README.md) for the project that uses it.

## How to run

Install Python 3 with PyTorch and Matplotlib:

```
pip install torch matplotlib
```

Run scripts from the repository root:

```
python3 basics/DARTS3.py
python3 basics/full-adder-discovery/DARTS4.py
python3 basics/sequence-detector/sequential.py
```

Each folder's README lists its options. The SPAD project lists its own packages in
[`SPAD/requirements.txt`](SPAD/requirements.txt) and its run steps in
[`SPAD/README.md`](SPAD/README.md).
