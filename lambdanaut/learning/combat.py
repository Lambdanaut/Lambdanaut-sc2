"""
For modelling sc2 combat and determining the victor in a fight.

Input = [[1,4], [4,2], [6,3] ...] aka [[player_1_unit_count, player_2_unit_count], [..], [..], ...]
Output = [0, 1, 0] Where [DRAW, PLAYER1 VICTORY, PLAYER2 VICTORY]

"""

import json
import os
import sys
from typing import List, Tuple

import sc2
import sc2.constants as const
import torch
import torch.nn as nn


DATA_DIR = 'data'
TRAINING_DATA_FILE = os.path.join(DATA_DIR, 'combat_zerg_v_zerg.json')
TESTING_DATA_FILE = os.path.join(DATA_DIR, 'combat_testing.json')

MODEL_FILE = os.path.join(DATA_DIR, 'combat_model.pt')


UNIT_INDEXES = {
    const.DRONE: 0,
    const.ZERGLING: 1,
    const.BANELING: 2,
    const.ROACH: 3,
    const.RAVAGER: 4,
    const.HYDRALISK: 5,
    const.QUEEN: 6,
    const.MUTALISK: 7,
    const.CORRUPTOR: 8,
    const.BROODLORD: 9,
    const.ULTRALISK: 10,
}


def load_training_json(filepath):
    with open(filepath, 'r') as f:
        contents = f.read()
        loaded = json.loads(contents)

    return loaded


def json_to_model_data(data: List[dict]) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Returns the (input data, output data, input_size) for training the model
    """
    inputs = []
    outputs = []

    input = []
    for training_sample in data:

        # Create an input the size of UNIT_INDEXES * 2 (For two players)
        input = [0 for _ in range(get_input_size())]

        for player in (1, 2):
            for unit_val, unit_count in training_sample[str(player)].items():
                unit_type_id = const.UnitTypeId(int(unit_val))

                # Add unit into the correct index in the input based on the player
                player_offset = len(UNIT_INDEXES) if player == 2 else 0

                input[UNIT_INDEXES[unit_type_id] + player_offset] = unit_count

        result = training_sample['result']

        # Add input to inputs list
        inputs.append(input)

        # Set the output result equal to 1
        output = [0, 0, 0]
        output[result] = 1

        outputs.append(output)

    inputs = torch.Tensor(inputs)
    outputs = torch.Tensor(outputs)

    return inputs, outputs


def units_to_model_data(units1, units2) -> torch.Tensor:

    # Create an input the size of UNIT_INDEXES * 2 (For two players)
    input = [0 for _ in range(get_input_size())]

    for player, unit_group in ((1, units1),  (2, units2)):
        for unit in unit_group:
            unit_type_id = unit.type_id

            # Add unit into the correct index in the input based on the player
            player_offset = len(UNIT_INDEXES) if player == 2 else 0

            unit_count = len(unit_group.of_type(unit_type_id))

            input[UNIT_INDEXES[unit_type_id] + player_offset] = unit_count

    # Wrap input in a list so we have a singleton 2D tensor
    input = [input]
    input = torch.Tensor(input)

    return input


def get_input_size():
    return len(UNIT_INDEXES) * 2


class Model(nn.Module):
    def __init__(self, D_in, H=150, D_out=3):
        super(Model, self).__init__()

        self.linear1 = torch.nn.Linear(in_features=D_in, out_features=H)
        self.relu1 = torch.nn.ReLU()
        self.linear2 = torch.nn.Linear(in_features=H, out_features=H)
        self.relu2 = torch.nn.ReLU()
        self.linear3 = torch.nn.Linear(in_features=H, out_features=D_out)

    def forward(self, input):
        output = self.linear1(input)
        output = self.relu1(output)
        output = self.linear2(output)
        output = self.relu2(output)
        output = self.linear3(output)
        return output

    def predict_victor(self, units1, units2) -> bool:
        """
        Returns true of units1 is predicted to win.
        Returns false otherwise, including if a draw is predicted.
        """

        # Convert units1 and units2 to a tensor
        units_tensor = units_to_model_data(units1, units2)

        # Run the input through the model
        victor_prediction = self(units_tensor)

        # Get the index of the predicted victor from the output tensor
        victor_prediction = (output_pred[0] == output_pred[0].max()).nonzero().item()

        # Only return true if we predict player 1 wins
        victor_prediction = {0: False, 1: True, 2: False}[victor_prediction]

        return victor_prediction


def save_model(filepath, model):
    torch.save(model.state_dict(), filepath)


def load_model(filepath=MODEL_FILE):
    input_size = len(UNIT_INDEXES) * 2  # Len of unit indexes for two players

    model = Model(input_size)
    model.load_state_dict(torch.load(filepath))
    model.eval()

    return model


def print_results(input, output_pred, output):
    correct_list = []

    for i in range(len(input)):
        print('== Iteration: {} =='.format(i))

        victor_result = (output[i] == output[i].max()).nonzero().item()
        print('OUTPUT: {}'.format(victor_result))

        victor_prediction = (output_pred[i] == output_pred[i].max()).nonzero().item()
        print('GREATEST PREDICTION: {}'.format(victor_prediction))

        print('INPUT: ')
        print(input[i])

        print('OUTPUT PREDICTION: ')
        print(output_pred[i])

        correct_list.append(victor_result == victor_prediction)

    print('List of correct predictions: ')
    print(correct_list)

    correct_prediction_ratio = len([x for x in correct_list if x]) / len(correct_list)
    print('Ratio of correct predictions: {}'.format(correct_prediction_ratio))


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

    print_results(testing_input, output_pred, testing_output)

    import pdb; pdb.set_trace()

    save_model(MODEL_FILE, model)


def train():
    # List of training data loaded from JSON
    training_list = load_training_json(TRAINING_DATA_FILE)

    # Tensor holding training data of form: [[1,4, ..], [4,2, .. ], [6,3, ..] ...]
    training_input, training_output = json_to_model_data(training_list)

    input_size = get_input_size()

    # Construct our model by instantiating the class defined above.
    model = Model(input_size)

    # Construct our loss function and an Optimizer. The call to model.parameters()
    # in the SGD constructor will contain the learnable parameters of the two
    # nn.Linear modules which are members of the model.
    loss_fn = torch.nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
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


def main():
    train()


if __name__ == '__main__':
    main()