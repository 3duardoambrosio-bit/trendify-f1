from infra.health_aggregator import HealthAggregator, HealthStatus


def test_health_check_healthy():
    aggregator = HealthAggregator()

    def healthy_check():
        return {"status": HealthStatus.HEALTHY, "details": "All good"}

    aggregator.register_check("test_service", healthy_check)
    health = aggregator.get_overall_health()

    assert health["status"] == HealthStatus.HEALTHY
    assert "test_service" in health["checks"]


def test_health_check_unhealthy():
    aggregator = HealthAggregator()

    def unhealthy_check():
        return {"status": HealthStatus.UNHEALTHY, "error": "Service down"}

    aggregator.register_check("test_service", unhealthy_check)
    health = aggregator.get_overall_health()

    assert health["status"] == HealthStatus.UNHEALTHY


def test_health_check_mixed():
    aggregator = HealthAggregator()

    def healthy_check():
        return {"status": HealthStatus.HEALTHY}

    def degraded_check():
        return {"status": HealthStatus.DEGRADED}

    aggregator.register_check("healthy_service", healthy_check)
    aggregator.register_check("degraded_service", degraded_check)
    health = aggregator.get_overall_health()

    assert health["status"] == HealthStatus.DEGRADED
