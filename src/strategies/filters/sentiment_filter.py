"""Sentiment analysis filter.

Integrates two data sources:

1. **Fear & Greed Index** – free API at ``api.alternative.me/fng/``
2. **VADER sentiment** on headlines from CryptoCompare news API

Results are cached in-memory with a configurable TTL so consecutive
calls during the same candle don't hammer the APIs.
"""

import time
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.strategies.base import TradeSignal, Signal
from src.strategies.filters import BaseFilter, FilterResult
from src.utils.logger import get_logger

logger = get_logger()

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    HAS_VADER = True
except ImportError:
    HAS_VADER = False


# ------------------------------------------------------------------
# Simple TTL cache
# ------------------------------------------------------------------

class _TTLCache:
    """Minimal in-memory cache with per-key TTL."""

    def __init__(self, ttl_seconds: float = 1800):
        self._store: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self.ttl = ttl_seconds

    def get(self, key: str):
        if key in self._store:
            if time.time() - self._timestamps[key] < self.ttl:
                return self._store[key]
            del self._store[key]
            del self._timestamps[key]
        return None

    def set(self, key: str, value: Any):
        self._store[key] = value
        self._timestamps[key] = time.time()


# ------------------------------------------------------------------
# Data fetchers
# ------------------------------------------------------------------

def fetch_fear_greed() -> Optional[Dict[str, Any]]:
    """Fetch latest Fear & Greed Index value.

    Returns ``{"value": int, "classification": str}`` or ``None``.
    """
    if not HAS_REQUESTS:
        return None
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            return {
                "value": int(data[0]["value"]),
                "classification": data[0].get("value_classification", ""),
            }
    except Exception as exc:
        logger.warning(f"Fear & Greed fetch failed: {exc}")
    return None


def fetch_crypto_news(api_key: str = "", limit: int = 20) -> Optional[list]:
    """Fetch recent crypto news headlines from CryptoCompare.

    A free tier key is optional but recommended.
    """
    if not HAS_REQUESTS:
        return None
    url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
    headers = {}
    if api_key:
        headers["authorization"] = f"Apikey {api_key}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("Data", [])
        return [{"title": a.get("title", ""), "body": a.get("body", "")[:500]}
                for a in articles[:limit]]
    except Exception as exc:
        logger.warning(f"CryptoCompare news fetch failed: {exc}")
    return None


def analyse_headlines(articles: list) -> float:
    """Return average VADER compound score for a list of articles.

    Score range: -1 (very negative) to +1 (very positive).
    """
    if not HAS_VADER or not articles:
        return 0.0
    analyser = SentimentIntensityAnalyzer()
    scores = []
    for article in articles:
        text = article.get("title", "")
        if text:
            scores.append(analyser.polarity_scores(text)["compound"])
    return float(np.mean(scores)) if scores else 0.0


# ------------------------------------------------------------------
# Sentiment filter
# ------------------------------------------------------------------

class SentimentFilter(BaseFilter):
    """Blocks signals when market sentiment is adverse.

    * Blocks **BUY** when Fear & Greed < ``fear_threshold`` (extreme fear)
      unless ``contrarian`` mode is enabled.
    * Blocks **SELL** when Fear & Greed > ``greed_threshold`` (extreme greed)
      unless ``contrarian`` mode is enabled.
    * Optionally requires news sentiment to agree with the signal direction.

    Parameters
    ----------
    fear_threshold : int
        Index value below which the market is in "extreme fear".
    greed_threshold : int
        Index value above which the market is in "extreme greed".
    news_api_key : str
        CryptoCompare API key (optional).
    news_sentiment_weight : float
        0-1 weight; 0 = ignore news, 1 = news only.
    contrarian : bool
        If True, inverts the logic (buy in fear, sell in greed).
    cache_ttl_minutes : int
        Minutes to cache API responses.
    """

    name = "Sentiment Filter"

    def __init__(
        self,
        fear_threshold: int = 25,
        greed_threshold: int = 75,
        news_api_key: str = "",
        news_sentiment_weight: float = 0.3,
        contrarian: bool = False,
        cache_ttl_minutes: int = 30,
        enabled: bool = True,
    ):
        super().__init__(enabled)
        self.fear_threshold = fear_threshold
        self.greed_threshold = greed_threshold
        self.news_api_key = news_api_key
        self.news_weight = news_sentiment_weight
        self.contrarian = contrarian
        self._cache = _TTLCache(ttl_seconds=cache_ttl_minutes * 60)

    def _get_fear_greed(self) -> Optional[int]:
        cached = self._cache.get("fng")
        if cached is not None:
            return cached
        data = fetch_fear_greed()
        if data:
            self._cache.set("fng", data["value"])
            return data["value"]
        return None

    def _get_news_sentiment(self) -> float:
        cached = self._cache.get("news_score")
        if cached is not None:
            return cached
        articles = fetch_crypto_news(self.news_api_key)
        if articles:
            score = analyse_headlines(articles)
            self._cache.set("news_score", score)
            return score
        return 0.0

    def apply(
        self,
        signal: TradeSignal,
        df: pd.DataFrame,
        index: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> FilterResult:
        if not self.enabled:
            return FilterResult(allow_signal=True)

        fng = self._get_fear_greed()
        news_score = self._get_news_sentiment() if self.news_weight > 0 else 0.0

        metadata: Dict[str, Any] = {
            "fear_greed_index": fng,
            "news_sentiment": news_score,
        }

        # If API is down, let the signal through
        if fng is None:
            return FilterResult(allow_signal=True, metadata=metadata)

        # Combined score: blend FNG (0-100) normalised to [-1,1] with news
        fng_normalised = (fng - 50) / 50  # -1 = extreme fear, +1 = extreme greed
        combined = fng_normalised * (1 - self.news_weight) + news_score * self.news_weight
        metadata["combined_score"] = round(combined, 3)

        if signal.signal == Signal.BUY:
            in_fear = fng < self.fear_threshold
            if self.contrarian:
                allow = in_fear or fng >= self.fear_threshold
            else:
                allow = not in_fear
            if not allow:
                return FilterResult(
                    allow_signal=False,
                    reason=f"Extreme fear (FNG={fng}), buy blocked",
                    metadata=metadata,
                )

        elif signal.signal == Signal.SELL:
            in_greed = fng > self.greed_threshold
            if self.contrarian:
                allow = in_greed or fng <= self.greed_threshold
            else:
                allow = not in_greed
            if not allow:
                return FilterResult(
                    allow_signal=False,
                    reason=f"Extreme greed (FNG={fng}), sell blocked",
                    metadata=metadata,
                )

        return FilterResult(allow_signal=True, metadata=metadata)
