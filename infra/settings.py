import os
from typing import Any, Dict
import yaml
from dotenv import load_dotenv

load_dotenv()


class Settings:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        # Cargar configuración por defecto de YAML
        with open("config/default.yml", "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        # Sobrescribir con variables de entorno
        self._override_with_env()

    def _override_with_env(self):
        # Environment
        if os.getenv("ENVIRONMENT"):
            self._config["environment"] = os.getenv("ENVIRONMENT")

        # Buyer
        if os.getenv("BUYER_MARGIN_THRESHOLD_MINIMUM"):
            self._config["buyer"]["margin_threshold"]["minimum"] = float(
                os.getenv("BUYER_MARGIN_THRESHOLD_MINIMUM")
            )
        if os.getenv("BUYER_MARGIN_THRESHOLD_PREFERRED"):
            self._config["buyer"]["margin_threshold"]["preferred"] = float(
                os.getenv("BUYER_MARGIN_THRESHOLD_PREFERRED")
            )
        if os.getenv("BUYER_MARGIN_THRESHOLD_REJECT_BELOW"):
            self._config["buyer"]["margin_threshold"]["reject_below"] = float(
                os.getenv("BUYER_MARGIN_THRESHOLD_REJECT_BELOW")
            )
        if os.getenv("BUYER_TRUST_THRESHOLD_MINIMUM"):
            self._config["buyer"]["trust_threshold"]["minimum"] = int(
                os.getenv("BUYER_TRUST_THRESHOLD_MINIMUM")
            )
        if os.getenv("BUYER_SUSPECT_PRICE_LOWER_MULTIPLIER"):
            self._config["buyer"]["suspect_price"]["lower_multiplier"] = float(
                os.getenv("BUYER_SUSPECT_PRICE_LOWER_MULTIPLIER")
            )
        if os.getenv("BUYER_SUSPECT_PRICE_UPPER_MULTIPLIER"):
            self._config["buyer"]["suspect_price"]["upper_multiplier"] = float(
                os.getenv("BUYER_SUSPECT_PRICE_UPPER_MULTIPLIER")
            )
        if os.getenv("BUYER_MAX_BATCH_SIZE"):
            self._config["buyer"]["max_batch_size"] = int(
                os.getenv("BUYER_MAX_BATCH_SIZE")
            )
        if os.getenv("BUYER_AI_FALLBACK_ENABLED"):
            self._config["buyer"]["ai_fallback_enabled"] = (
                os.getenv("BUYER_AI_FALLBACK_ENABLED").lower() == "true"
            )

        # Logging
        if os.getenv("LOG_LEVEL"):
            self._config["logging"]["level"] = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_FORMAT"):
            self._config["logging"]["format"] = os.getenv("LOG_FORMAT")

        # Operational
        if os.getenv("MAINTENANCE_MODE"):
            self._config["operational"]["maintenance_mode"] = (
                os.getenv("MAINTENANCE_MODE").lower() == "true"
            )
        if os.getenv("DEBUG_LOGGING"):
            self._config["operational"]["debug_logging"] = (
                os.getenv("DEBUG_LOGGING").lower() == "true"
            )

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value: Any = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def config(self) -> Dict[str, Any]:
        return self._config


settings = Settings()
