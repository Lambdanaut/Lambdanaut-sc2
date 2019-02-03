"""
For modelling sc2 combat and determining the victor in a fight.

Input = [[1,4], [4,2], [6,3] ...] aka [[player_1_unit_count, player_2_unit_count], [..], [..], ...]
Output = [0, 1, 0] Where [DRAW, PLAYER1 VICTORY, PLAYER2 VICTORY]

"""

import json
import os
from typing import List, Tuple

import sc2
import sc2.constants as const
import torch
import torch.nn as nn
from torch.optim import Adam
import numpy as np


DATA_DIR = 'data'
TRAINING_DATA_FILE = os.path.join(DATA_DIR, 'combat.json')
TESTING_DATA_FILE = os.path.join(DATA_DIR, 'combat_testing.json')


def load_training_json(filepath):
    with open(filepath, 'r') as f:
        contents = f.read()
        loaded = json.loads(contents)

    return loaded


def json_to_model_data(data: List[dict]) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Returns the (input data, output data) for training the model
    """
    inputs = []
    outputs = []
    for training_sample in data:
        p1_zergling_count = training_sample['1'][str(const.ZERGLING.value)]
        p2_zergling_count = training_sample['2'][str(const.ZERGLING.value)]

        result = training_sample['result']

        inputs.append([
            p1_zergling_count,
            p2_zergling_count,
        ])

        # Set the output result equal to 1
        output = [0, 0, 0]
        output[result] = 1

        outputs.append(output)

    inputs = torch.Tensor(inputs)
    outputs = torch.Tensor(outputs)

    return inputs, outputs


class Model(nn.Module):
    def __init__(self, D_in, H, D_out):
        super(Model, self).__init__()

        self.linear1 = torch.nn.Linear(in_features=D_in, out_features=H)
        self.linear2 = torch.nn.Linear(in_features=H, out_features=D_out)
        self.relu = torch.nn.ReLU()

    def forward(self, input):
        output = self.linear1(input)
        output = self.relu(output)
        output = self.linear2(output)
        return output


def do_testing(model):
    # List of testing data loaded from JSON
    testing_list = load_training_json(TESTING_DATA_FILE)

    # Tensor holding testing data
    testing_input, testing_output = json_to_model_data(testing_list)

    # Construct our loss function and an Optimizer. The call to model.parameters()
    # in the SGD constructor will contain the learnable parameters of the two
    # nn.Linear modules which are members of the model.
    loss_fn = torch.nn.MSELoss()

    output_pred = model(testing_input)

    # Compute and print loss
    loss = loss_fn(output_pred, testing_output)
    print("Loss: {}".format(loss.item()))
    print(output_pred)

    import pdb; pdb.set_trace()



def main():
    # List of training data loaded from JSON
    training_list = load_training_json(TRAINING_DATA_FILE)

    # Tensor holding training data of form: [[1,4], [4,2], [6,3] ...]
    training_input, training_output = json_to_model_data(training_list)

    # D_in is input dimension;
    # H is hidden dimension; D_out is output dimension.
    N, D_in, H, D_out = len(training_list), 2, 100, 3

    # Construct our model by instantiating the class defined above.
    model = Model(D_in, H, D_out)

    # Construct our loss function and an Optimizer. The call to model.parameters()
    # in the SGD constructor will contain the learnable parameters of the two
    # nn.Linear modules which are members of the model.
    loss_fn = torch.nn.MSELoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)
    for t in range(1000):
        # Forward pass: Compute predicted output by passing input to the model
        output_pred = model(training_input)

        # Compute and print loss
        loss = loss_fn(output_pred, training_output)
        print(t, loss.item())

        # Zero gradients, perform a backward pass, and update the weights.
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    print("============TRAINING COMPLETE============")
    print("Starting testing...")

    do_testing(model)


if __name__ == '__main__':
    main()