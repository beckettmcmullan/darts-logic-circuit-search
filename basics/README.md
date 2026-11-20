# DARTS basics

Early experiments, in the order they were written. Each step adds one idea.
The last two apply DARTS to logic circuits. Each script has a docstring at the
top that explains it in more detail.

DARTS (differentiable architecture search) makes a discrete choice, such as
"which operation goes here", differentiable. Every candidate gets a score. A
softmax turns the scores into probabilities. The output is the
probability-weighted sum of all candidates. Gradient descent then trains the
scores along with the ordinary weights. At the end, each choice is replaced by
its highest-probability candidate (argmax).

Run everything from the repository root with PyTorch installed.

## The progression

| Step | File | What it adds | Run |
|---|---|---|---|
| 0 | [`test.py`](test.py) | Not DARTS. One linear layer trained with SGD on one point. It shows the training loop. | `python3 basics/test.py` |
| 1 | [`firstDARTS.py`](firstDARTS.py) | A softmax mix of two operations (identity and a linear layer). The scores are learned along with the layer's weights. | `python3 basics/firstDARTS.py` |
| 2 | [`DARTS2.py`](DARTS2.py) | A small neural network as the second operation, four data points, Adam, and a final argmax to pick one operation. | `python3 basics/DARTS2.py` |
| 3 | [`DARTS3.py`](DARTS3.py) | A graph of 4 nodes. Every edge between an earlier and a later node mixes four operations (zero, identity, linear, nonlinear). Separate lists of weight parameters and architecture parameters. The argmax is taken per edge. | `python3 basics/DARTS3.py` |
| 4 | [`full-adder-discovery/`](full-adder-discovery/README.md) | The candidates become logic gates. Each node learns which gate it is and which earlier signals it reads. The target is a full adder truth table. Many circuits train in one batch. The final circuit is checked on all 8 inputs. | `python3 basics/full-adder-discovery/DARTS4.py` |
| 5 | [`sequence-detector/`](sequence-detector/README.md) | Memory. D flip-flops let the circuit use earlier inputs. The target is a detector for the bit pattern 1011. Area and delay costs are added to the loss. The final circuit is verified exhaustively. | `python3 basics/sequence-detector/sequential.py` |

Steps 0 to 3 are quick and print to the terminal. Steps 4 and 5 train 64
circuits at once and write figures. Step 5 also writes `history.json`. Step 4
opens a matplotlib window at the end, so close it to let the script exit.

## What changes from step to step

- Steps 1 and 2 use a mix of operations on one number. The mix is learned.
- Step 3 repeats the mix on every edge of a small acyclic graph. It also splits
  the parameters into weights (inside the operations) and architecture
  parameters (the scores). Both are still trained together.
- Step 4 swaps the operations for logic gates. Gates are written as arithmetic
  on 0/1 values, for example AND = a * b and XOR = a + b - 2ab. These are exact
  on 0 and 1 and smooth in between. The wiring is also learned: each gate input
  is a softmax-weighted sum of all earlier signals. A mask blocks later nodes,
  so the circuit has no loops.
- Step 5 adds clocked memory and a hardware-cost term. See its README.

The main project, [`SPAD/`](../SPAD/README.md), builds on the step 4 and 5 ideas.
