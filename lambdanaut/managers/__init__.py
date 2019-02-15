from typing import Any, Optional

import lambdanaut.bot
from lambdanaut.const2 import Messages
import lambdanaut.const2 as const2


class Manager(object):
    """
    Base class for all AI managers
    """

    name = 'Manager'

    # Managers can receive messages by subscribing to certain events
    # with self.subscribe(EVENT_NAME)

    def __init__(self, bot):
        self.bot: lambdanaut.bot.LambdaBot = bot

        self._messages = {}

    async def init(self):
        """
        To be called after init in order to publish messages and do setup
        that touches other Managers
        """
        pass

    def inbox(self, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Send a message of message_type to this manager
        """
        self._messages[message_type] = value

    @property
    def messages(self):
        return self._messages.copy()

    def ack(self, message_type):
        """
        Messages must be acknowledged to remove them from the inbox
        """
        self.print('Message acked: {}'.format(message_type.name))
        self._messages.pop(message_type)

    def subscribe(self, message_type: const2.Messages):
        """
        Subscribe to a message of message_type
        """
        return self.bot.subscribe(self, message_type)

    def publish(self, message_type: const2.Messages, value: Optional[Any] = None):
        """
        Publish a message to all subscribers of it's type
        """
        self.print('Message published: {} - {}'.format(message_type.name, value))
        return self.bot.publish(self, message_type, value)

    async def read_messages(self):
        """
        Overwrite this function to read all incoming messages
        """
        pass

    def print(self, msg):
        print('{}: {}'.format(self.name, msg))

    async def run(self):
        pass


class StatefulManager(Manager):
    """
    Base class for all state-machine AI managers
    """

    # Default starting state to set in Manager
    state = None
    # The previous state
    previous_state = None

    # Maps to overwrite with state-machine functions
    state_map = {}
    # Map of functions to do when entering the state
    state_start_map = {}
    # Map of functions to do when leaving the state
    state_stop_map = {}

    async def determine_state_change(self):
        raise NotImplementedError

    async def change_state(self, new_state):
        """
        Changes the state and runs a start and stop function if specified
        in self.state_start_map or self.state_stop_map"""

        self.print('State changed to: {}'.format(new_state.name))

        # Run a start function for the new state if it's specified
        start_function = self.state_start_map.get(new_state)
        if start_function:
            await start_function()

        # Run a stop function for the current state if it's specified
        stop_function = self.state_stop_map.get(self.state)
        if stop_function:
            await stop_function()

        # Set the previous state to the current state
        self.previous_state = self.state

        # Set the new state
        self.state = new_state

        # Publish message about state change
        self.publish(Messages.STATE_ENTERED, self.state)
        self.publish(Messages.STATE_EXITED, self.previous_state)

    async def run_state(self):
        # Run function for current state
        state_f = self.state_map.get(self.state)
        if state_f is not None:
            return await state_f()

    async def run(self):
        await self.determine_state_change()
        await self.run_state()


