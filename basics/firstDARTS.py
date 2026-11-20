"""First DARTS idea: a softmax-weighted choice between two operations.

Two candidate operations act on the same input:
  A: identity (output = input)
  B: a linear layer (output = input * weight + bias)

The architecture parameters are `learning_scores`, one score per operation.
A softmax turns them into probabilities that sum to 1, and the prediction is the
probability-weighted sum of both outputs. Because the sum is smooth, the loss
gradient reaches the scores as well as the layer's own weights, so training
learns which operation to prefer. The target is y = 4 for x = 2, which identity
cannot produce, so probability should shift toward B.

There is no final "pick one" step here. The script only prints the probabilities.

Run: python3 basics/firstDARTS.py
"""
import torch
from torch import nn

operation_A = nn.Identity() #output = input
operation_B = nn.Linear(1,1) #output = input * weight + bias

# learnable parameters for weighting operations A and B
learning_scores = nn.Parameter(torch.zeros(2)) 

x = torch.tensor([2.0]) # input to the network
y = torch.tensor([4.0])  # target output

# optimize both the operation parameters and the learning scores
optimizer = torch.optim.SGD(list(operation_B.parameters()) + [learning_scores], lr=0.01) 

for step in range(1000):
    optimizer.zero_grad()
    probabilities = nn.Softmax(dim=0)(learning_scores) # compute probabilities for operations A and B
    prediction_A = operation_A(x) # output from operation A
    prediction_B = operation_B(x) # output from operation B
    prediction = probabilities[0] * prediction_A + probabilities[1] * prediction_B # weighted sum of outputs from operations A and B
    loss = nn.MSELoss()(prediction, y) # compute loss
    loss.backward() # back propagate to compute how sensitive loss function is to changes in weight, bias, and learning scores
    optimizer.step() # update weights using SGD

    if step % 100 == 0:
        print(f'Step {step}: loss = {loss.item()}: prediction = {prediction.item()}')
        print(f'Probabilities: A = {probabilities[0].item()}, B = {probabilities[1].item()}')