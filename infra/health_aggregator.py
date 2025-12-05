from typing import Dict, Any, Callable
from enum import Enum
import time


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthAggregator:
    def __init__(self) -> None:
        self._checks: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def register_check(self, name: str, check_func: Callable[[], Dict[str, Any]]) -> None:
        self._checks[name] = check_func

    def get_overall_health(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        unhealthy_count = 0
        degraded_count = 0

        for name, check_func in self._checks.items():
            try:
                result = check_func()
                results[name] = result

                status = result.get("status")
                if status == HealthStatus.UNHEALTHY:
                    unhealthy_count += 1
                elif status == HealthStatus.DEGRADED:
                    degraded_count += 1

            except Exception as e:  # noqa: BLE001
                results[name] = {
                    "status": HealthStatus.UNHEALTHY,
                    "error": str(e),
                }
                unhealthy_count += 1

        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "status": overall_status,
            "checks": results,
            "timestamp": time.time(),
        }


# Global instance
health_aggregator = HealthAggregator()
