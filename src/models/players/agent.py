import json
import random
import time
from typing import List, Optional, Tuple

from src.models.action import Action, ActionType, ChallengeAction, NoChallengeAction, CounterAction, NoCounterAction, RemoveCardAction
from src.models.card import Card
from src.models.players.base import BasePlayer
from src.utils.print import print_text, print_texts

from src.models.memory import Memory
import openai


class AgentPlayer(BasePlayer):
    is_ai: bool = True
    personality: str
    memory: Memory
    inner_thoughts: str

    def _system_msg(self, overall_task: str, possible_actions: List[Action], possible_players: List[BasePlayer], task: str) -> str:
        possible_actions_str = [str(action.action_type.value) for action in possible_actions]
        possible_players_str = [(str(player.name) + " has " + str(len(player.cards)) + " cards.") for player in possible_players]

        system_msg = f"""You are a player in the board game 'Coup'. Your name is {self.name} and you have the following personality:
{self.personality}

You have the following inner thoughts and overall strategy:
{self.inner_thoughts}

Your overall task is to decide the following:
{overall_task}

Here are the possible actions:
{possible_actions_str}

Here are the possible players that you can act on:
{possible_players_str}

Some actions do not require choosing a player.

Your task is to decide the following:
{task}"""

        return system_msg

    def _alter_thoughts(self, messages: List) -> str:
        # Make a call to the llm to alter the inner thoughts based on the new thoughts, action and player
        task = f"""You have now thought about the current state of the game and your overall strategy.
        
Alter your inner thoughts based on the new thoughts, action and player. Output your thoughts in a clear and concise manner.

Inner thoughts:
{self.inner_thoughts}"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )

        new_inner_thoughts = response.choices[0].text.strip()
        return new_inner_thoughts

    def make_decision(self, overall_task: str, possible_actions: List[Action], possible_players: List[BasePlayer], messages: List, decision_type: str):
        """
        Options:
        1. Separator + parsing actions
        2. GPT functions
        3. JSON mode <- opted for this one for simplicity
        4. Use embedding to match raw text to actions
        """
        if decision_type == "action":
            required_json = [
                {
                    "name": "action",
                    "type": "string",
                    "required": True,
                    "enum": [action.action_type.value for action in possible_actions]
                },
                {
                    "name": "player",
                    "type": "string",
                    "required": False,
                    "enum": [player.name for player in possible_players]
                }
            ]
        elif decision_type == "challenge":
            required_json = [
                {
                    "name": "challenge",
                    "type": "boolean",
                    "required": True,
                    "enum": [True, False]
                }
            ]
        elif decision_type == "counter":
            required_json = [
                {
                    "name": "counter",
                    "type": "boolean",
                    "required": True,
                    "enum": [True, False]
                }
            ]

        elif decision_type == "remove_card":
            required_json = [
                {
                    "name": "card_to_remove",
                    "type": "string",
                    "required": True,
                    "enum": [card.card_type.value for card in self.cards]
                }
            ]
        elif decision_type == "exchange_cards":
            required_json = [
                {
                    "name": "card_1",
                    "type": "string",
                    "required": True,
                    "enum": [card.card_type.value for card in self.cards]
                },
                {
                    "name": "card_2",
                    "type": "string",
                    "required": True,
                    "enum": [card.card_type.value for card in self.cards]
                }
            ]
        else:
            raise ValueError("Invalid decision type")

        task = f"""You have now thought about the current state of the game and your overall strategy.

        You must now make a decision based on your thoughts. Output your decision according to the following format:
{required_json}"""

        system_msg = self._system_msg(overall_task, possible_actions, possible_players, task)
        messages.append({"role": "system", "content": system_msg})

        for i in range(3):
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                response_format={"type": "json_object"}
            )

            content = response.choices[0].text.strip()

            try:
                json_content = json.loads(content)
            except json.JSONDecodeError:
                messages.append({"role": "system", "content": f"""Could not parse the following json:
{content}
Please try again and provide the json in the correct format\n"""})
                continue

            feedback_str = ""
            for item in required_json:
                if item["required"] and item["name"] not in json_content:
                    feedback_str += f"Please try again and provide the {item['name']} in the correct format\n"
                elif item["required"] and json_content[item["name"]] not in item["enum"]:
                    feedback_str += f"Invalid {item['name']}. Please try again and choose from the possible options: {item['enum']}\n"

            if feedback_str:
                messages.append({"role": "system", "content": feedback_str})
                continue

            if decision_type == "action":
                action = next((a for a in possible_actions if a.action_type.value == json_content["action"]), None)
                player = next((p for p in possible_players if p.name == json_content["player"]), None)

                if action.action_type == ActionType.steal and player.coins == 0:
                    messages.append({"role": "system", "content": "You can't steal from a player with 0 coins. Please try again"})
                    continue

                return action, player
            elif decision_type == "challenge":
                return json_content["challenge"] == "True"
            elif decision_type == "counter":
                return json_content["counter"] == "True"
            elif decision_type == "remove_card":
                card = next((c for c in self.cards if c.card_type.value == json_content["card_to_remove"]), None)
                return card
            elif decision_type == "exchange_cards":
                card_1 = next((c for c in self.cards if c.card_type.value == json_content["card_1"]), None)
                card_2 = next((c for c in self.cards if c.card_type.value == json_content["card_2"]), None)
                return card_1, card_2

                # Fail case, just do a random action
        return None

    def add_new_thought_to_messages(self, overall_task: str, possible_actions: List[Action or Card], possible_players: List[BasePlayer]) -> List:
        task = """Think about the current state of the game and your overall strategy.

Think step by step about how you can achieve this goal. Output your thoughts in a clear and concise manner."""
        system_msg = self._system_msg(overall_task, possible_actions, possible_players, task)
        messages = [
            {"role": "system", "content": system_msg}
        ]

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        new_thought = response.choices[0].text.strip()

        self.inner_thoughts = self._alter_thoughts(new_thought)

        messages.append({"role": "assistant", "content": new_thought})

        return messages

    def choose_action(self, other_players: List[BasePlayer]) -> Tuple[Action, Optional[BasePlayer]]:
        """Choose the next action to perform"""
        available_actions = self.available_actions()

        print_text(f"[bold magenta]{self}[/] is thinking...", with_markup=True)
        time.sleep(1)

        # Coup is only option
        if len(available_actions) == 1:
            overall_task = "You must coup because you have more than 10 coins. Choose a player to coup."
            messages = self.add_new_thought_to_messages(overall_task, available_actions, other_players)
            decision = self.make_decision(overall_task, available_actions, other_players, messages, "action")
            if decision is not None:
                return decision
        else:
            overall_task = "Choose an action to perform"
            messages = self.add_new_thought_to_messages(overall_task, available_actions, other_players)
            decision = self.make_decision(overall_task, available_actions, other_players, messages, "action")
            if decision is not None:
                return decision

        # Fail case, just do a random action
        target_player = None
        while True:
            target_action = random.choice(available_actions)
            if target_action.requires_target:
                target_player = random.choice(other_players)

            if self._validate_action(target_action, target_player):
                return target_action, target_player

    def react_to_action(self, event: str, is_current_player: bool) -> str:
        """
        Make changes to internal thoughts + output something you want to say (could be nothing)
        """
        system_msg = f"""You are {self.name}.

You are playing a game of Coup.

{"You just made the following move:" if is_current_player else "The following event just happened:"}
{event}

{"Why did you make this move?" if is_current_player else "What is your reaction & thoughts on this event and what might you say to the other players?"}"""

        event_thoughts = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg}
            ]
        )

        return event_thoughts.choices[0].message.content

    def adjust_internal_thoughts(self, event: str, is_current_player:bool, conversation: str) -> None:
        """
        Adjust internal thoughts based on the event and conversation that just happened
        """
        system_msg = f"""You are {self.name}.
        
You are playing a game of Coup.

{"You just made the following move:" if is_current_player else "The following event just happened:"}
{event}

After the event, the following conversation took place:
{conversation}

Here are your current inner thoughts:
{self.inner_thoughts}

Adjust your inner thoughts based on the event and conversation. Output your thoughts in a clear and concise manner."""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg}
            ]
        )

        self.inner_thoughts = response.choices[0].message.content


    def determine_challenge(self, player: BasePlayer) -> bool:
        """Choose whether to challenge the current player"""
        messages = self.add_new_thought_to_messages("Do you want to challenge the current player on their move?", [ChallengeAction(), NoChallengeAction()], [player])
        challenge = self.make_decision("Do you want to challenge the current player on their move?", [ChallengeAction(), NoChallengeAction()], [player], messages, "challenge")
        if challenge is not None:
            return challenge

        return random.randint(0, 4) == 0

    def determine_counter(self, player: BasePlayer) -> bool:
        """Choose whether to counter the current player's action"""

        messages = self.add_new_thought_to_messages("Do you want to counter the current player's move?", [CounterAction(), NoCounterAction()], [player])
        counter = self.make_decision("Do you want to counter the current player's move?", [CounterAction(), NoCounterAction()], [player], messages, "counter")
        if counter is not None:
            return counter

        return random.randint(0, 9) == 0

    def remove_card(self) -> None:
        """Choose a card and remove it from your hand"""
        remove_card_actions = [RemoveCardAction(card=card.card_type) for card in self.cards]

        messages = self.add_new_thought_to_messages("You must choose a card to remove from your hand", remove_card_actions, [])
        card_to_remove = self.make_decision("You must choose a card to remove from your hand", remove_card_actions, [], messages, "remove_card")
        if card_to_remove:
            for card in self.cards:
                if card.card_type == card_to_remove.card_type:
                    self.cards.remove(card)
                    break

            print_texts(f"{self} discards their ", (f"{card_to_remove}", card_to_remove.style), " card")
            return

        # Fail case, just do a random action
        discarded_card = self.cards.pop(random.randrange(len(self.cards)))
        print_texts(f"{self} discards their ", (f"{discarded_card}", discarded_card.style), " card")

    def choose_exchange_cards(self, exchange_cards: list[Card]) -> Tuple[Card, Card]:
        """Perform the exchange action. Pick which 2 cards to send back to the deck"""

        self.cards += exchange_cards
        random.shuffle(self.cards)
        remove_card_actions = [RemoveCardAction(card=card.card_type) for card in self.cards]
        messages = self.add_new_thought_to_messages("You have drawn 2 cards from the deck, but you have to give 2 back", remove_card_actions, [])
        cards = self.make_decision("You have drawn 2 cards from the deck, but you have to give 2 back", remove_card_actions, [], messages, "exchange_cards")
        print_text(f"{self} exchanges 2 cards")
        if cards is not None:
            (card_1, card_2) = cards
            for card in self.cards:
                if card.card_type == card_1.card_type:
                    self.cards.remove(card)
                    break

            for card in self.cards:
                if card.card_type == card_2.card_type:
                    self.cards.remove(card)
                    break
            return card_1, card_2

        return self.cards.pop(), self.cards.pop()
