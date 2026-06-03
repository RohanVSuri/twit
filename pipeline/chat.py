"""
RAG chat — answers questions grounded in a day's tweets.

Embeds the user's question, retrieves the k most similar tweets from the
FAISS store, then sends them to Haiku with the RAG_CHAT_PROMPT.
"""

from __future__ import annotations

import anthropic
from dotenv import load_dotenv

load_dotenv()

from pipeline.embed import Embedder
from pipeline.prompts import RAG_CHAT_PROMPT
from store.faiss_store import FAISSStore


class ChatSession:
    def __init__(
        self,
        store: FAISSStore,
        embedder: Embedder,
        date: str,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.date = date
        self.model = model
        self.client = anthropic.Anthropic()

    def ask(self, question: str, k: int = 20) -> str:
        """
        Answer a question grounded in the day's tweets.

        Args:
            question: Natural language question from the user.
            k:        Number of tweets to retrieve from FAISS.

        Returns:
            Answer string from Haiku, with source URLs appended.
        """
        q_embedding = self.embedder.embed_query(question)
        tweets = self.store.query(q_embedding, k=k)

        tweet_list = "\n".join(
            f"[{t['id']} | {t['url']}] {t['text']}" for t in tweets
        )

        prompt = RAG_CHAT_PROMPT.format(
            date=self.date,
            tweet_list=tweet_list,
            question=question,
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
