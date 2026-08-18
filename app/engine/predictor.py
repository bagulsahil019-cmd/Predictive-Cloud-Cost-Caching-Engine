import time
import numpy as np
from sklearn.linear_model import Ridge

class TrafficPredictor:
    def __init__(self, window_seconds: float = 60.0, bin_seconds: float = 10.0):
        self.window_seconds = window_seconds
        self.bin_seconds = bin_seconds
        # Record request timestamps for each key: key -> list of float timestamps
        self.request_history = {}
        # Track EMA of request rate: key -> float (requests per second)
        self.ema_rates = {}
        self.alpha = 0.3  # EMA smoothing factor
        self.last_request_time = {}
        
        # Scikit-learn model parameters
        self.model = Ridge(alpha=1.0)
        self.is_trained = False
        
        # To train the model, we collect global training samples of [c_t-1, c_t-2, c_t-3] -> total_next_window
        # We store these as lists
        self.X_train = []
        self.y_train = []
        self.max_training_samples = 200

    def record_request(self, key: str) -> None:
        """Records a request occurrence for a key and updates the EMA rate."""
        now = time.time()
        if key not in self.request_history:
            self.request_history[key] = []
        self.request_history[key].append(now)
        
        # Update EMA rate
        if key in self.last_request_time:
            dt = now - self.last_request_time[key]
            if dt > 0:
                inst_rate = 1.0 / dt
                current_ema = self.ema_rates.get(key, inst_rate)
                self.ema_rates[key] = self.alpha * inst_rate + (1 - self.alpha) * current_ema
        else:
            self.ema_rates[key] = 1.0 / self.window_seconds  # Initial low rate estimate
            
        self.last_request_time[key] = now
        self._clean_history(key, now)
        self._update_training_data(key, now)

    def _clean_history(self, key: str, now: float) -> None:
        """Keeps only the requests in the last 10 minutes to save memory."""
        cutoff = now - 600.0
        self.request_history[key] = [t for t in self.request_history[key] if t > cutoff]

    def _update_training_data(self, key: str, now: float) -> None:
        """
        Periodically creates training samples from the history of requests.
        A sample is: features = counts in [now-30, now-20], [now-20, now-10], [now-10, now]
                     target = count in [now, now+60]
        To do this online, we can look at historical slices (e.g., at time now - 60).
        """
        # We only generate a training sample when we have a reasonable amount of data for the key.
        history = self.request_history[key]
        if len(history) < 10:
            return
            
        # Let's generate a sample anchored at (now - 60) so we can measure the actual target in [now-60, now]
        anchor = now - self.window_seconds
        
        # Features relative to anchor: counts in bins of size bin_seconds
        # Feature bins: [anchor - 30, anchor - 20], [anchor - 20, anchor - 10], [anchor - 10, anchor]
        bins = [
            (anchor - 30.0, anchor - 20.0),
            (anchor - 20.0, anchor - 10.0),
            (anchor - 10.0, anchor)
        ]
        
        features = []
        for start, end in bins:
            count = sum(1 for t in history if start <= t < end)
            features.append(count)
            
        # Target: count in [anchor, anchor + window_seconds] (which is [anchor, now])
        target = sum(1 for t in history if anchor <= t <= now)
        
        self.X_train.append(features)
        self.y_train.append(target)
        
        # Limit size
        if len(self.X_train) > self.max_training_samples:
            self.X_train.pop(0)
            self.y_train.pop(0)
            
        # Train model if we have enough samples
        if len(self.X_train) >= 15 and len(self.X_train) % 5 == 0:
            try:
                self.model.fit(np.array(self.X_train), np.array(self.y_train))
                self.is_trained = True
            except Exception:
                self.is_trained = False

    def predict_frequency(self, key: str) -> float:
        """
        Predicts the number of requests for a key in the next window_seconds.
        Uses scikit-learn Ridge regression if trained, otherwise falls back to EMA.
        """
        now = time.time()
        history = self.request_history.get(key, [])
        
        # If no history or very little, return minimal prediction
        if not history:
            return 1.0

        # Decay EMA if it has been a long time since the last request
        last_t = self.last_request_time.get(key, now)
        idle_time = now - last_t
        ema_rate = self.ema_rates.get(key, 1.0 / self.window_seconds)
        
        if idle_time > 10.0:
            # Decay the rate exponentially based on how long it has been idle
            ema_rate = ema_rate * np.exp(-0.05 * idle_time)
            self.ema_rates[key] = ema_rate

        # Get features for the current time
        # Feature bins: [now - 30, now - 20], [now - 20, now - 10], [now - 10, now]
        bins = [
            (now - 30.0, now - 20.0),
            (now - 20.0, now - 10.0),
            (now - 10.0, now)
        ]
        
        features = []
        for start, end in bins:
            count = sum(1 for t in history if start <= t < end)
            features.append(count)
            
        if self.is_trained:
            try:
                pred = self.model.predict(np.array([features]))[0]
                # Ensure prediction is positive and reasonable
                ema_fallback = ema_rate * self.window_seconds
                # Blend prediction with EMA to prevent extreme outliers and ensure responsiveness
                final_pred = 0.7 * pred + 0.3 * ema_fallback
                return float(max(1.0, final_pred))
            except Exception:
                pass
                
        # EMA fallback: rate * window_seconds
        return float(max(1.0, ema_rate * self.window_seconds))
