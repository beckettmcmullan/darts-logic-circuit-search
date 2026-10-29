import torch
from torch import nn

num_nodes = 4 # nodes 0 - 3 -> with edges 0->1, 0->2, 1->2, 0->3, 1->3, 2->3

class Zero(nn.Module):
    def forward(self, x):
        return 0 * x

operation_names = ['zero', 'identity', 'linear', 'nonlinear']
def make_operations(): # make fresh copies of every operation at every edge of a node
    return nn.ModuleList([
        Zero(), # index 0: output = 0
        nn.Identity(), # index 1: output = input
        nn.Linear(1,1), # index 2: output = input * weight + bias
        nn.Sequential( # index 3: learn a nonlinear relationship
            nn.Linear(1,16),
            nn.Tanh(),
            nn.Linear(16,1),
        ),
        ])

class MixedEdge(nn.Module): # 1 connection between 2 nodes
    def __init__(self):
        super().__init__()
        self.operations = make_operations() # each edge has its own weights for each operation
        self.scores = nn.Parameter(torch.zeros(len(self.operations))) # architecture scores for each operation at every edge

    def forward(self, x):
        probabilities = torch.softmax(self.scores, dim=0) # the probabilities of each operation at every edge
        return sum(probabilities[k] * op(x) for k, op in enumerate(self.operations)) # weighted sum of outputs of all operations at a edge

class Cell(nn.Module):
    def __init__(self, num_nodes):
        super().__init__()
        self.num_nodes = num_nodes
        # one MixedEdge per (i, j) pair with i < j, stored under a name like "0->2"
        self.edges = nn.ModuleDict({
            f'{i}->{j}': MixedEdge() for j in range(1, num_nodes) for i in range(j)
        })

    def forward(self, x):
        nodes = [x] # node 0 is the input
        for j in range(1, self.num_nodes):
            nodes.append(sum(self.edges[f'{i}->{j}'](nodes[i]) for i in range(j))) # node j = sum of its incoming edges
        return nodes[-1] # the last node is the output

    def architecture_parameters(self): # the scores of every edge
        return [edge.scores for edge in self.edges.values()]

    def weight_parameters(self): # the weights inside every operation
        return [p for edge in self.edges.values() for p in edge.operations.parameters()]

torch.manual_seed(0) # same result every run

x = torch.linspace(-2, 2, 32).unsqueeze(1) # 32 inputs, one feature each
y = x ** 2 + x # matching output shape

cell = Cell(num_nodes)
optimizer = torch.optim.Adam(cell.weight_parameters() + cell.architecture_parameters(), lr=0.01) # one optimizer for weights and scores, like DARTS2.py

def print_edges():
    with torch.no_grad():
        for name, edge in cell.edges.items():
            probabilities = torch.softmax(edge.scores, dim=0)
            formatted = ', '.join(f'{operation_names[k]}={p:.3f}' for k, p in enumerate(probabilities.tolist()))
            print(f'  edge {name}: {formatted}')

for step in range(3000):
    optimizer.zero_grad() # clear gradients
    prediction = cell(x) # run the whole cell
    loss = nn.MSELoss()(prediction, y) # compute loss
    loss.backward() # gradients flow to every edge's weights and scores
    optimizer.step() # update weights and scores using Adam
    if step % 1000 == 0 or step == 2999:
        print(f'Step {step}: loss = {loss.item():.5f}')
        print_edges()

with torch.no_grad(): # pick the most likely operation on each edge, independently
    print('Chosen operation per edge:')
    for name, edge in cell.edges.items():
        best_operation = torch.argmax(edge.scores).item()
        print(f'  edge {name}: {operation_names[best_operation]}')
