from functools import lru_cache

import annoy
import openai
import json


class Memory:
    def __init__(self, player):
        self.player = player
        self.index = annoy.AnnoyIndex(1536, 'angular')
        self.index.load(f'{player.name}.ann')
        self.metadata = json.load(open(f'{player.name}.json'))

    @lru_cache
    def embed(self, text):
        return openai.Embedding.retrieve(text=text).vector


    def calculate_importance(self, text):
        system_msg = f"""You are {self.player.name}.
        
You are playing a game of coup with some friends.

Your current emotional state is:
{self.player.emotional_state}

The following thing just happened:
{text}

How important is this event to you on a scale of 1 to 10? (1 being not important at all, 10 being extremely important)
"""

    def add(self, text):
        embedding = self.embed(text)



        self.index.add_item(self.index.get_n_items(), embedding)
        self.metadata[self.index.get_n_items()] = text

    def query(self, embedding, k):
        return self.index.get_nns_by_vector(embedding, k)
