"""Langfuse tracing wrapper. Every LLM call and agent action logs through here."""
import os
from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

_client = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


def trace(name: str, input: dict | None = None, metadata: dict | None = None):
    return _client.trace(name=name, input=input, metadata=metadata)


def flush():
    _client.flush()
