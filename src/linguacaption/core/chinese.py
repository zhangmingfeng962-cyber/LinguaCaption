"""Normalize Chinese captions locally; other languages keep their own characters."""
from functools import lru_cache

from opencc import OpenCC


@lru_cache(maxsize=1)
def _converter() -> OpenCC:
    return OpenCC("t2s")


def simplified(text: str, language: str) -> str:
    return _converter().convert(text) if text and language == "zh" else text
