from __future__ import annotations

import re

from nltk.tokenize import RegexpTokenizer
from pymorphy3 import MorphAnalyzer

from src.api.services.audiance.constants import STOPWORDS


class AudienceTextProcessor:
    def __init__(self, *, generic_cluster_tokens: set[str] | None = None) -> None:
        self._lemma_cache: dict[str, str] = {}
        self._morph = MorphAnalyzer()
        self._tokenizer = RegexpTokenizer(r"[A-Za-zА-Яа-яЁё]{4,}")
        self._generic_cluster_tokens = generic_cluster_tokens or set()

    def tokenize(self, text: str) -> list[str]:
        raw_tokens = self.extract_raw_tokens(text)
        normalized_tokens: list[str] = []
        for raw_token in raw_tokens:
            token = self.lemmatize_token(raw_token)
            if len(token) < 4:
                continue
            if raw_token in STOPWORDS or token in STOPWORDS:
                continue
            normalized_tokens.append(token)
        return normalized_tokens

    def lemmatize_token(self, token: str) -> str:
        cached = self._lemma_cache.get(token)
        if cached is not None:
            return cached

        if re.fullmatch(r"[а-яё]+", token):
            normalized = self._morph.parse(token)[0].normal_form
        elif re.fullmatch(r"[a-z]+", token):
            normalized = self.normalize_english_token(token)
        else:
            normalized = token

        self._lemma_cache[token] = normalized
        return normalized

    def extract_raw_tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        return [token for token in self._tokenizer.tokenize(lowered) if token.isalpha()]

    @staticmethod
    def language_weight(token: str, pattern: str) -> float:
        token_has_cyrillic = bool(re.search(r"[а-яё]", token))
        pattern_has_cyrillic = bool(re.search(r"[а-яё]", pattern))
        token_has_latin = bool(re.search(r"[a-z]", token))
        pattern_has_latin = bool(re.search(r"[a-z]", pattern))

        if token_has_cyrillic and pattern_has_cyrillic:
            return 1.0
        if token_has_latin and pattern_has_latin and not token_has_cyrillic and not pattern_has_cyrillic:
            return 0.55
        return 0.8

    @staticmethod
    def normalize_english_token(token: str) -> str:
        for suffix in ("ingly", "edly", "ing", "ed", "ies", "es", "s"):
            if len(token) - len(suffix) >= 4 and token.endswith(suffix):
                if suffix == "ies":
                    return token[:-3] + "y"
                return token[:-len(suffix)]
        return token

    def is_meaningful_token(self, token: str) -> bool:
        normalized = token.strip().lower()
        return (
            len(normalized) >= 4
            and normalized not in STOPWORDS
            and normalized not in self._generic_cluster_tokens
        )

    def is_meaningful_phrase(self, phrase: str) -> bool:
        parts = [part for part in phrase.lower().split() if part]
        if len(parts) < 2:
            return False
        meaningful_parts = [part for part in parts if self.is_meaningful_token(part)]
        return len(meaningful_parts) == len(parts)

    def is_meaningful_note(self, text: str) -> bool:
        normalized = text.strip().lower()
        if " " in normalized:
            return self.is_meaningful_phrase(normalized)
        return self.is_meaningful_token(normalized)
