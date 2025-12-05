from typing import Dict, Any, List


class MetricsCollector:
    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def increment_counter(
        self, name: str, labels: Dict[str, str] | None = None, value: int = 1
    ) -> None:
        key = self._format_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def set_gauge(
        self, name: str, labels: Dict[str, str] | None = None, value: float = 0
    ) -> None:
        key = self._format_key(name, labels)
        self._gauges[key] = value

    def observe_histogram(
        self, name: str, labels: Dict[str, str] | None = None, value: float = 0
    ) -> None:
        key = self._format_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def _format_key(self, name: str, labels: Dict[str, str] | None = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "counters": self._counters.copy(),
            "gauges": self._gauges.copy(),
            "histograms": {k: v.copy() for k, v in self._histograms.items()},
        }


# Global instance
metrics_collector = MetricsCollector()
