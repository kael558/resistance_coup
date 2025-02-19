from typing import List

from rich.panel import Panel
from rich.table import Column, Table
from rich.text import Text

from src.models.card import Card
from src.models.players.agent import AgentPlayer
from src.models.players.human import BasePlayer


def generate_str_panel(conversation: str) -> Panel:
    """Generate a panel showing the conversation"""
    return Panel(
        conversation,
        title=":speech_balloon: Conversation",
        width=50,
    )

def generate_player_panel(player: BasePlayer) -> Panel:
    """Generate a panel showing the player's information"""
    name = Text.from_markup(f":grimacing: {player.name}")
    name.stylize("bold magenta")
    personal_coins = Text(f"Coins: {player.coins}", style="gray")

    if isinstance(player, AgentPlayer):
        personality = Text("Personality: " + player.personality, style="gray")
        inner_thoughts = Text("Inner Thoughts: " + player.inner_thoughts, style="gray")
        cards = Text("Cards: " + ", ".join([str(card) for card in player.cards]), style="gray")

        return Panel(
            f"""
{name}
{personal_coins}
{personality}
{inner_thoughts}
{cards}
 """,
            title=":robot: Agent Player",
        )
    else:
        return Panel(
            f"""
{name}
{personal_coins}
            """
        )

def generate_state_panel(
    deck: list[Card], treasury_coins: int, current_player: BasePlayer
) -> Panel:
    """Generate a panel showing some game information"""
    return Panel(
        f"""
:game_die: Deck: {len(deck)} cards

:moneybag: Treasury: {treasury_coins} coins

:person_tipping_hand: Current Player: [bold magenta]{current_player}
""",
        width=50,
    )


def generate_players_table(players: List[BasePlayer], current_player_index: int) -> Table:
    """Generate a table of the players"""

    table = Table("Players", "Coins", Column(header="Cards", justify="center", min_width=40))
    for ind, player in enumerate(players):
        if player.is_ai:
            player_text = Text.from_markup(f":robot: {str(player)}")
        else:
            player_text = Text.from_markup(f":grimacing: {str(player)}")

        if ind == current_player_index:
            player_text.stylize("bold magenta")

        coin_text = Text(str(player.coins), style="gray")

        card_text = Text()
        if player.is_active:
            for card in player.cards:
                if player.is_ai:
                    card_text.append("<Secret...> ")
                else:
                    card_text.append(
                        str(card), style=f"{card.foreground_color} on {card.background_color}"
                    )
                    card_text.append(" ")
        else:
            card_text = Text.from_markup(":skull:")

        table.add_row(player_text, coin_text, card_text)

    return table
