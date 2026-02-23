"""Machine-learning signal filters.

Provides two filter implementations:

* **MLSignalFilter** – classical ML (scikit-learn): Random Forest or
  Gradient Boosting trained on engineered features extracted at signal time.
* **LSTMSignalFilter** – lightweight PyTorch LSTM that consumes the last
  *N* candles (with indicators) and outputs a confidence score.

Both inherit from ``BaseFilter`` and plug into the existing ``FilterChain``
/ ``FilteredStrategy`` infrastructure.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.strategies.base import TradeSignal, Signal
from src.strategies.filters import BaseFilter, FilterResult
from src.utils.logger import get_logger

logger = get_logger()

# Optional heavy imports – filters degrade gracefully when unavailable.
try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report
    import joblib
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


# ------------------------------------------------------------------
# Feature engineering helpers
# ------------------------------------------------------------------

def _engineer_features(df: pd.DataFrame, index: int, lookback: int = 20) -> Optional[np.ndarray]:
    """Extract a fixed-width feature vector for bar *index*.

    Returns ``None`` if not enough history.
    """
    if index < lookback:
        return None

    window = df.iloc[index - lookback: index + 1]
    close = window["close"].values
    high = window["high"].values
    low = window["low"].values
    volume = window["volume"].values

    ret_1 = (close[-1] / close[-2] - 1) if close[-2] != 0 else 0
    ret_5 = (close[-1] / close[-6] - 1) if len(close) > 5 and close[-6] != 0 else 0
    ret_10 = (close[-1] / close[-11] - 1) if len(close) > 10 and close[-11] != 0 else 0

    volatility = np.std(np.diff(close) / close[:-1]) if len(close) > 1 else 0
    avg_volume = np.mean(volume[:-1]) if len(volume) > 1 else 1
    vol_ratio = volume[-1] / avg_volume if avg_volume > 0 else 1

    atr_vals = high - low
    atr = np.mean(atr_vals[-14:]) if len(atr_vals) >= 14 else np.mean(atr_vals)
    atr_ratio = atr / close[-1] if close[-1] > 0 else 0

    # RSI (simple)
    deltas = np.diff(close)
    gain = np.mean(np.maximum(deltas[-14:], 0)) if len(deltas) >= 14 else 0
    loss = np.mean(np.maximum(-deltas[-14:], 0)) if len(deltas) >= 14 else 1e-10
    rsi = 100 - 100 / (1 + gain / (loss + 1e-10))

    # Bollinger width
    sma20 = np.mean(close[-20:])
    std20 = np.std(close[-20:])
    bb_width = (2 * std20 / sma20) if sma20 > 0 else 0

    features = np.array([
        ret_1, ret_5, ret_10,
        volatility, vol_ratio, atr_ratio,
        rsi / 100,
        bb_width,
    ], dtype=np.float32)

    return features


def _build_training_set(
    df: pd.DataFrame,
    trade_indices: List[int],
    trade_labels: List[int],
    lookback: int = 20,
):
    """Build X, y arrays from trade signal indices and their labels."""
    X, y = [], []
    for idx, label in zip(trade_indices, trade_labels):
        feat = _engineer_features(df, idx, lookback)
        if feat is not None:
            X.append(feat)
            y.append(label)
    return np.array(X), np.array(y)


# ------------------------------------------------------------------
# Classical ML filter
# ------------------------------------------------------------------

class MLSignalFilter(BaseFilter):
    """Signal filter powered by scikit-learn classifiers.

    Usage::

        filt = MLSignalFilter(model_type="gradient_boosting")
        filt.train(df, trades)        # train on historical data
        filt.save_model("data/models/ml_filter.pkl")

        # later …
        filt.load_model("data/models/ml_filter.pkl")
        result = filt.apply(signal, df, index)
    """

    name = "ML Signal Filter"

    def __init__(
        self,
        model_type: str = "gradient_boosting",
        confidence_threshold: float = 0.55,
        lookback: int = 20,
        enabled: bool = True,
    ):
        super().__init__(enabled)
        self.model_type = model_type
        self.confidence_threshold = confidence_threshold
        self.lookback = lookback
        self._model = None
        self._trained = False

    def train(
        self,
        df: pd.DataFrame,
        trade_indices: List[int],
        trade_labels: List[int],
    ) -> Dict[str, Any]:
        """Train the classifier.

        Parameters
        ----------
        df : OHLCV DataFrame (with indicators already calculated).
        trade_indices : bar indices where signals were generated.
        trade_labels : 1 = profitable trade, 0 = losing trade.

        Returns
        -------
        dict with training accuracy, test accuracy, classification report.
        """
        if not HAS_SKLEARN:
            raise RuntimeError("scikit-learn is required for MLSignalFilter.train()")

        X, y = _build_training_set(df, trade_indices, trade_labels, self.lookback)
        if len(X) < 10:
            raise ValueError(f"Not enough samples to train ({len(X)})")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y if len(set(y)) > 1 else None,
        )

        if self.model_type == "random_forest":
            model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        else:
            model = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)

        model.fit(X_train, y_train)
        self._model = model
        self._trained = True

        train_acc = accuracy_score(y_train, model.predict(X_train))
        test_acc = accuracy_score(y_test, model.predict(X_test))

        logger.info(f"ML filter trained: train_acc={train_acc:.3f}  test_acc={test_acc:.3f}")
        return {
            "train_accuracy": train_acc,
            "test_accuracy": test_acc,
            "n_samples": len(X),
            "report": classification_report(y_test, model.predict(X_test), output_dict=True),
        }

    def apply(self, signal: TradeSignal, df: pd.DataFrame, index: int,
              context: Optional[Dict[str, Any]] = None) -> FilterResult:
        if not self.enabled or not self._trained or self._model is None:
            return FilterResult(allow_signal=True)

        feat = _engineer_features(df, index, self.lookback)
        if feat is None:
            return FilterResult(allow_signal=True, metadata={"reason": "insufficient_history"})

        proba = self._model.predict_proba(feat.reshape(1, -1))[0]
        confidence = proba[1] if len(proba) > 1 else proba[0]

        allow = confidence >= self.confidence_threshold
        return FilterResult(
            allow_signal=allow,
            reason="" if allow else f"ML confidence {confidence:.2f} < {self.confidence_threshold}",
            metadata={"ml_confidence": float(confidence), "model_type": self.model_type},
        )

    def save_model(self, path: str) -> None:
        if not HAS_SKLEARN:
            raise RuntimeError("scikit-learn required")
        if self._model is None:
            raise ValueError("No model to save")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, path)
        logger.info(f"ML model saved to {path}")

    def load_model(self, path: str) -> None:
        if not HAS_SKLEARN:
            raise RuntimeError("scikit-learn required")
        self._model = joblib.load(path)
        self._trained = True
        logger.info(f"ML model loaded from {path}")

    def get_required_history(self) -> int:
        return self.lookback + 5


# ------------------------------------------------------------------
# LSTM filter (PyTorch)
# ------------------------------------------------------------------

class _LSTMNet(nn.Module if HAS_TORCH else object):
    """Lightweight LSTM for signal confidence prediction."""

    def __init__(self, input_size: int = 8, hidden_size: int = 32,
                 num_layers: int = 1, dropout: float = 0.1):
        if not HAS_TORCH:
            return
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, dropout=dropout if num_layers > 1 else 0)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        return self.fc(h_n[-1]).squeeze(-1)


class LSTMSignalFilter(BaseFilter):
    """Signal filter using a small LSTM network (PyTorch).

    The network takes a sequence of *seq_len* feature vectors and
    outputs a confidence score in [0, 1].
    """

    name = "LSTM Signal Filter"

    def __init__(
        self,
        seq_len: int = 20,
        hidden_size: int = 32,
        confidence_threshold: float = 0.55,
        enabled: bool = True,
    ):
        super().__init__(enabled)
        self.seq_len = seq_len
        self.hidden_size = hidden_size
        self.confidence_threshold = confidence_threshold
        self._model: Optional[Any] = None
        self._trained = False

    def _build_sequence(self, df: pd.DataFrame, index: int) -> Optional[np.ndarray]:
        """Build a (seq_len, n_features) array ending at *index*."""
        seqs = []
        for i in range(index - self.seq_len + 1, index + 1):
            feat = _engineer_features(df, i, lookback=20)
            if feat is None:
                return None
            seqs.append(feat)
        return np.array(seqs, dtype=np.float32)

    def train(
        self,
        df: pd.DataFrame,
        trade_indices: List[int],
        trade_labels: List[int],
        epochs: int = 30,
        lr: float = 1e-3,
        batch_size: int = 32,
    ) -> Dict[str, Any]:
        """Train the LSTM on historical signal data."""
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is required for LSTMSignalFilter.train()")

        sequences, labels = [], []
        for idx, label in zip(trade_indices, trade_labels):
            seq = self._build_sequence(df, idx)
            if seq is not None:
                sequences.append(seq)
                labels.append(label)

        if len(sequences) < 10:
            raise ValueError(f"Not enough sequences to train ({len(sequences)})")

        X = torch.tensor(np.array(sequences), dtype=torch.float32)
        y = torch.tensor(np.array(labels), dtype=torch.float32)

        n_features = X.shape[2]
        model = _LSTMNet(input_size=n_features, hidden_size=self.hidden_size)
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        criterion = nn.BCELoss()

        model.train()
        history = []
        for epoch in range(epochs):
            perm = torch.randperm(len(X))
            epoch_loss = 0.0
            for start in range(0, len(X), batch_size):
                batch_idx = perm[start: start + batch_size]
                xb, yb = X[batch_idx], y[batch_idx]
                pred = model(xb)
                loss = criterion(pred, yb)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            history.append(epoch_loss)

        model.eval()
        with torch.no_grad():
            preds = model(X)
            acc = ((preds > 0.5).float() == y).float().mean().item()

        self._model = model
        self._trained = True
        logger.info(f"LSTM filter trained: accuracy={acc:.3f}  epochs={epochs}")
        return {"accuracy": acc, "final_loss": history[-1], "n_samples": len(X)}

    def apply(self, signal: TradeSignal, df: pd.DataFrame, index: int,
              context: Optional[Dict[str, Any]] = None) -> FilterResult:
        if not self.enabled or not self._trained or self._model is None:
            return FilterResult(allow_signal=True)
        if not HAS_TORCH:
            return FilterResult(allow_signal=True)

        seq = self._build_sequence(df, index)
        if seq is None:
            return FilterResult(allow_signal=True, metadata={"reason": "insufficient_history"})

        x = torch.tensor(seq, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            confidence = self._model(x).item()

        allow = confidence >= self.confidence_threshold
        return FilterResult(
            allow_signal=allow,
            reason="" if allow else f"LSTM confidence {confidence:.2f} < {self.confidence_threshold}",
            metadata={"lstm_confidence": float(confidence)},
        )

    def save_model(self, path: str) -> None:
        if not HAS_TORCH or self._model is None:
            raise RuntimeError("No model to save")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(self._model.state_dict(), path)
        logger.info(f"LSTM model saved to {path}")

    def load_model(self, path: str, n_features: int = 8) -> None:
        if not HAS_TORCH:
            raise RuntimeError("PyTorch required")
        model = _LSTMNet(input_size=n_features, hidden_size=self.hidden_size)
        model.load_state_dict(torch.load(path, weights_only=True))
        model.eval()
        self._model = model
        self._trained = True
        logger.info(f"LSTM model loaded from {path}")

    def get_required_history(self) -> int:
        return self.seq_len + 25
