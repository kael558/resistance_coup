from datetime import datetime
from functools import lru_cache

import openai
import json

from src.utils.helpers import cosine_similarity, min_max_normalize


class Memory:
    def __init__(self, player):
        self.player = player
        self.memories = json.load(open(f'{player.name}.json'))

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

Output just the number.
"""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg}
            ]
        )

        return response.choices[0].message.content

    def add(self, text):
        embedding = self.embed(text)
        importance = self.calculate_importance(text)

        self.memories.append({
            'text': text,
            'importance': importance,
            'date': datetime.now().isoformat(),
            'embedding': embedding
        })

    def get(self, user_message_embed):
        recency_scores = []
        relevance_scores = []
        importance_scores = []

        current_time = datetime.now().timestamp()

        for memory in self.memories:
            timestamp = datetime.fromisoformat(memory['timestamp']).timestamp()
            recency_score = timestamp * ((current_time - timestamp) / 1000)
            recency_scores.append(recency_score)

            relevance_score = 1 - cosine_similarity([user_message_embed], [memory['embed']])[0][0]
            relevance_scores.append(relevance_score)

            importance_scores.append(memory['importanceScore'])

        normalized_recency = min_max_normalize(recency_scores)
        normalized_relevance = min_max_normalize(relevance_scores)
        normalized_importance = min_max_normalize(importance_scores)

        alpha_recency = 0.5
        alpha_relevance = 0.5
        alpha_importance = 1.0 # Importance is the most important factor

        retrieval_scores = []

        for i in range(len(self.memories)):
            retrieval_score = (alpha_recency * normalized_recency[i] +
                               alpha_relevance * (1 - normalized_relevance[i]) +
                               alpha_importance * normalized_importance[i])
            retrieval_scores.append((self.memories[i]['value'], retrieval_score))

        # Sort by retrieval score in descending order and take top 10
        top_memories = sorted(retrieval_scores, key=lambda x: x[1], reverse=True)[:10]

        # Convert memories to string representation and join them
        result = ", ".join([m[0] for m in top_memories])

        print(f"MemoryDB: Returning {result}")
        return result



