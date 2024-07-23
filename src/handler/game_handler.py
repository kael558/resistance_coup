import random
from enum import Enum
from typing import List, Optional, Tuple, Union

import names

from src.models.action import Action, ActionType, CounterAction, get_counter_action
from src.models.card import Card, build_deck
from src.models.players.ai import AIPlayer
from src.models.players.base import BasePlayer
from src.models.players.human import HumanPlayer
from src.models.players.agent import AgentPlayer
from src.utils.game_state import generate_players_table, generate_state_panel, generate_player_panel, generate_str_panel
from src.utils.print import (
    build_action_report_string,
    build_counter_report_string,
    print_confirm,
    print_panel,
    print_table,
    print_text,
    print_texts,
)

from src.utils.api_interface import client


class ChallengeResult(Enum):
    no_challenge = 0
    challenge_failed = 1
    challenge_succeeded = 2


class ResistanceCoupGameHandler:
    _players: List[BasePlayer] = []
    _current_player_index = 0
    _deck: List[Card] = []
    _number_of_players: int = 0
    _treasury: int = 0

    def __init__(self, number_of_players: int):

        self._number_of_players = number_of_players
        unique_names = set()
        for i in range(number_of_players):
            gender = random.choice(["male", "female"])

            ai_name = names.get_first_name(gender=gender)
            while ai_name in unique_names:
                ai_name = names.get_first_name(gender=gender)

            unique_names.add(ai_name)

            personality = names.generate_personality(ai_name, gender)

            self._players.append(AgentPlayer(name=ai_name, personality=personality))

    @property
    def current_player(self) -> BasePlayer:
        return self._players[self._current_player_index]

    @property
    def remaining_player(self) -> BasePlayer:
        """Return the only remaining player"""
        return [player for player in self._players if player.is_active][0]

    def print_player_state(self, player_index: int) -> None:
        print_panel(generate_player_panel(self._players[player_index]))

    def print_game_state(self) -> None:
        print_table(generate_players_table(self._players, self._current_player_index))
        print_panel(generate_state_panel(self._deck, self._treasury, self.current_player))

    def _players_without_player(self, excluded_player: BasePlayer):
        players_copy = self._players.copy()
        return [
            player
            for player in players_copy
            if player.is_active and player.name != excluded_player.name
        ]

    def _shuffle_deck(self) -> None:
        random.shuffle(self._deck)

    def setup_game(self) -> None:
        self._deck = build_deck()
        self._shuffle_deck()

        self._treasury = 50 - 2 * len(self._players)

        for player in self._players:
            player.reset_player()

            # Deal 2 cards to each player
            player.cards.append(self._deck.pop())
            player.cards.append(self._deck.pop())

            # Gives each player 2 coins
            player.coins = 2

            # Includes the player in the game
            player.is_active = True

        # Random starting player
        self._current_player_index = random.randint(0, self._number_of_players - 1)

    def _swap_card(self, player: BasePlayer, card: Card) -> None:
        self._deck.append(card)
        self._shuffle_deck()
        player.cards.append(self._deck.pop())

    def _take_coin_from_treasury(self, player: BasePlayer, number_of_coins: int):
        if number_of_coins <= self._treasury:
            self._treasury -= number_of_coins
            player.coins += number_of_coins
        else:
            coins = self._treasury
            self._treasury = 0
            player.coins += coins

    def _give_coin_to_treasury(self, player: BasePlayer, number_of_coins: int):
        self._treasury += number_of_coins
        player.coins -= number_of_coins

    def _next_player(self):
        self._current_player_index = (self._current_player_index + 1) % len(self._players)
        while not self.current_player.is_active:
            self._current_player_index = (self._current_player_index + 1) % len(self._players)

    def _remove_defeated_player(self) -> Optional[BasePlayer]:
        for ind, player in enumerate(self._players):
            if not player.cards and player.is_active:
                player.is_active = False
                self._give_coin_to_treasury(player, player.coins)

                return player
        return None

    def _determine_win_state(self) -> bool:
        return sum(player.is_active for player in self._players) == 1

    def _action_phase(
            self, players_without_current: list[BasePlayer]
    ) -> Tuple[Action, Optional[BasePlayer]]:
        # Player chooses action
        target_action, target_player = self.current_player.choose_action(players_without_current)

        print_text(
            build_action_report_string(
                player=self.current_player, action=target_action, target_player=target_player
            ),
            with_markup=True,
        )

        return target_action, target_player

    def _challenge_against_player_failed(
            self, player_being_challenged: BasePlayer, card: Card, challenger: BasePlayer, action_being_challenged: Union[Action, CounterAction]
    ):
        # Player being challenged reveals the card
        print_texts(f"{player_being_challenged} reveals their ", (f"{card}", card.style), " card!")
        print_text(f"{challenger} loses the challenge")

        evt = f"{challenger} challenged {player_being_challenged}'s on attempting action {action_being_challenged}... {player_being_challenged} had the required card so {challenger} loses the challenge"
        self.send_event_to_players(evt)

        # Challenge player loses influence (chooses a card to remove)
        challenger.remove_card()

        # Player puts card into the deck and gets a new card
        print_text(f"{player_being_challenged} gets a new card")
        self._swap_card(player_being_challenged, card)

    def _challenge_against_player_succeeded(self, player_being_challenged: BasePlayer, action_being_challenged: Action, challenger: BasePlayer):
        print_text(f"{player_being_challenged} bluffed! They do not have the required card!")

        evt = f"{challenger} challenged {player_being_challenged}'s on attempting action {action_being_challenged}... {player_being_challenged} did not have the required card so {challenger} wins the challenge"
        self.send_event_to_players(evt)

        # Player being challenged loses influence (chooses a card to remove)
        player_being_challenged.remove_card()

    def _challenge_phase(
            self,
            other_players: list[BasePlayer],
            player_being_challenged: BasePlayer,
            action_being_challenged: Union[Action, CounterAction],
    ) -> ChallengeResult:
        # Every player can choose to challenge
        for challenger in other_players:
            should_challenge = challenger.determine_challenge(player_being_challenged, action_being_challenged)
            if should_challenge:
                if challenger.is_ai:
                    print_text(f"{challenger} is challenging {player_being_challenged}!")
                # Player being challenged has the card
                if card := player_being_challenged.find_card(
                        action_being_challenged.associated_card_type
                ):


                    self._challenge_against_player_failed(
                        player_being_challenged=player_being_challenged,
                        card=card,
                        challenger=challenger,
                        action_being_challenged=action_being_challenged,
                    )

                    return ChallengeResult.challenge_failed

                # Player being challenged bluffed
                else:
                    self._challenge_against_player_succeeded(player_being_challenged, action_being_challenged, challenger)
                    return ChallengeResult.challenge_succeeded

        # No challenge happened
        return ChallengeResult.no_challenge

    def _counter_phase(
            self, players_without_current: list[BasePlayer], target_action: Action
    ) -> Tuple[Optional[BasePlayer], Optional[CounterAction]]:
        # Every player can choose to counter
        for countering_player in players_without_current:
            should_counter = countering_player.determine_counter(self.current_player, target_action)
            if should_counter:
                target_counter = get_counter_action(target_action.action_type)
                print_text(
                    build_counter_report_string(
                        target_player=self.current_player,
                        counter=target_counter,
                        countering_player=countering_player,
                    )
                )

                return countering_player, target_counter

        return None, None

    def _execute_action(
            self, action: Action, target_player: BasePlayer, countered: bool = False
    ) -> None:
        match action.action_type:
            case ActionType.income:
                # Player gets 1 coin
                self._take_coin_from_treasury(self.current_player, 1)
                print_text(f"{self.current_player}'s coins are increased by 1")
            case ActionType.foreign_aid:
                if not countered:
                    # Player gets 2 coin
                    self._take_coin_from_treasury(self.current_player, 2)
                    print_text(f"{self.current_player}'s coins are increased by 2")
            case ActionType.coup:
                # Player pays 7 coin
                self._give_coin_to_treasury(self.current_player, 7)
                print_text(
                    f"{self.current_player} pays 7 coins and performs the coup against {target_player}"
                )

                if target_player.cards:
                    # Target player loses influence
                    target_player.remove_card()
            case ActionType.tax:
                # Player gets 3 coins
                self._take_coin_from_treasury(self.current_player, 3)
                print_text(f"{self.current_player}'s coins are increased by 3")
            case ActionType.assassinate:
                # Player pays 3 coin
                self._give_coin_to_treasury(self.current_player, 3)
                if not countered and target_player.cards:
                    print_text(f"{self.current_player} assassinates {target_player}")
                    target_player.remove_card()
            case ActionType.steal:
                if not countered:
                    # Take 2 (or all) coins from a player
                    steal_amount = min(target_player.coins, 2)
                    target_player.coins -= steal_amount
                    self.current_player.coins += steal_amount
                    print_text(
                        f"{self.current_player} steals {steal_amount} coins from {target_player}"
                    )
            case ActionType.exchange:
                # Get 2 random cards from deck
                cards = [self._deck.pop(), self._deck.pop()]
                first_card, second_card = self.current_player.choose_exchange_cards(cards)
                self._deck.append(first_card)
                self._deck.append(second_card)

    def _generate_conversation(self, evt: str, player_thoughts: list[str]):
        print_text(f"Event just happened: {evt}")

        player_specs = [f"""---{player.name}--- 
Personality: {player.personality}
Inner thoughts: {thought}""" for player, thought in zip(self._players, player_thoughts)]

        player_specs = "\n".join(player_specs)

        system_msg = f"""You will generate a realistic conversation about the following group of players playing the board game Coup.

The conversation should be in a script format.

Here is what just happened:
{evt}

Here is each players' personality & inner thoughts on the event:
{player_specs}

Depending on the personality and inner thoughts of each player, they may lie, bluff, or tell the truth, or try to influence the other players.

The conversation should only be between the current players and should not proceed to any actions.

The purpose of the conversation is for players to convey their thoughts, desires to other players (to influence and convince them). But it is not a requirement that everyone has to speak.
DO NOT PLAY THE ACTUAL GAME, JUST THE CONVERSATION PART.

Write the conversation below:"""
        conversation = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg}
            ]
        )

        return conversation.choices[0].message.content

    def send_event_to_players(self, event: str):
        """
        1. Send the action to all players to react
        2. Retrieve their input
        3. Construct a conversation
        4. Adjust all players internal thoughts based on conversation
        """

        # Send the event to all players to react
        player_thoughts = []
        for player in self._players:
            player_thought = player.react_to_action(event, is_current_player=player == self.current_player)
            player_thoughts.append(player_thought)

        # Construct a conversation
        conversation = self._generate_conversation(event, player_thoughts)

        print_panel(generate_str_panel(conversation), justify="left")

        # Adjust all players internal thoughts based on conversation following event
        for player, player_thought in zip(self._players, player_thoughts):
            player.adjust_internal_thoughts(event, is_current_player=player == self.current_player, conversation=conversation)

    def handle_turn(self) -> bool:
        players_without_current = self._players_without_player(self.current_player)

        # Choose an action to perform
        target_action, target_player = self._action_phase(players_without_current)

        if target_player:
            evt = "Player {} is attempting to perform action {} on player {}".format(self.current_player, target_action, target_player)
        else:
            evt = "Player {} is attempting to perform action {}".format(self.current_player, target_action)
        self.send_event_to_players(evt)

        # Opportunity to challenge action
        challenge_result = ChallengeResult.no_challenge
        if target_action.can_be_challenged:
            challenge_result = self._challenge_phase(
                other_players=players_without_current,
                player_being_challenged=self.current_player,
                action_being_challenged=target_action,
            )

        if challenge_result == ChallengeResult.challenge_succeeded:
            # Challenge succeeded and the action does not take place
            pass
        elif challenge_result == ChallengeResult.challenge_failed:
            # Challenge failed and the action is still resolved
            self._execute_action(target_action, target_player)
        elif challenge_result == ChallengeResult.no_challenge:

            # Action can't be countered
            if not target_action.can_be_countered:
                #evt = "Player {} did not challenge player {}'s action {} and the action cannot be countered".format(self.current_player, target_player, target_action)
                #self.send_event_to_players(evt)
                self._execute_action(target_action, target_player)

            # Opportunity to counter
            else:
                countering_player, counter = self._counter_phase(
                    players_without_current, target_action
                )

                # Opportunity to challenge counter
                counter_challenge_result = ChallengeResult.no_challenge
                if countering_player and counter:
                    players_without_countering_player = self._players_without_player(
                        countering_player
                    )
                    counter_challenge_result = self._challenge_phase(
                        other_players=players_without_countering_player,
                        player_being_challenged=countering_player,
                        action_being_challenged=counter,
                    )

                # Successfully countered and counter not challenged
                if counter and counter_challenge_result in [
                    ChallengeResult.no_challenge,
                    ChallengeResult.challenge_failed,
                ]:

                    self._execute_action(target_action, target_player, countered=True)
                # No counter occurred
                else:

                    self._execute_action(target_action, target_player)

        # Is any player out of the game?
        while player := self._remove_defeated_player():
            if player.is_ai:
                print_text(f"{player} was defeated! :skull: :skull: :skull:", with_markup=True)
            else:
                # Our human was defeated
                print_text("You were defeated! :skull: :skull: :skull:", with_markup=True)
                end_game = print_confirm("Do you want to end the game early?")
                if end_game:
                    return True

        # Have we reached a winner?
        if self._determine_win_state():
            print_text(
                f":raising_hands: Congratulations {self.remaining_player}! You are the final survivor!",
                with_markup=True,
            )
            return True

        self._next_player()

        # No winner yet
        return False
