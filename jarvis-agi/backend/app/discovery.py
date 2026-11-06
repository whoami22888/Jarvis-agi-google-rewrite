import ipaddress
import logging
from urllib.parse import urlparse

from zeroconf import ServiceInfo, Zeroconf

from .config import Settings

LOGGER = logging.getLogger(__name__)
SERVICE_TYPE = "_whiterabbit-gateway._tcp.local."


class GatewayAdvertiser:
    """Opt-in local-network advertisement for a gateway that remains independently authenticated."""

    def __init__(self, config: Settings):
        self._config = config
        self._zeroconf: Zeroconf | None = None
        self._service: ServiceInfo | None = None

    @property
    def enabled(self) -> bool:
        return self._config.gateway_discovery_enabled

    def start(self) -> None:
        if not self.enabled:
            return
        try:
            gateway_url, port = _validated_gateway_url(self._config.gateway_discovery_url)
            address = ipaddress.ip_address(self._config.gateway_discovery_address).packed
            display_name = self._config.gateway_discovery_name or "WhiteRabbit Gateway"
            service_name = f"{display_name}.{SERVICE_TYPE}"
            self._service = ServiceInfo(
                type_=SERVICE_TYPE,
                name=service_name,
                port=port,
                properties={"url": gateway_url, "version": "1"},
                addresses=[address],
            )
            self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._service, allow_name_change=True)
            LOGGER.info("Local gateway discovery advertisement enabled for %s", display_name)
        except Exception as exc:
            self.stop()
            LOGGER.warning("Gateway discovery advertisement was not started: %s", exc)

    def stop(self) -> None:
        if self._zeroconf and self._service:
            try:
                self._zeroconf.unregister_service(self._service)
            except Exception:
                LOGGER.debug("Gateway discovery advertisement was already unavailable", exc_info=True)
        if self._zeroconf:
            self._zeroconf.close()
        self._service = None
        self._zeroconf = None


def _validated_gateway_url(raw_url: str) -> tuple[str, int]:
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("GATEWAY_DISCOVERY_URL must be a complete HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("GATEWAY_DISCOVERY_URL must not include credentials, a query, or a fragment")
    return raw_url.rstrip("/"), parsed.port or 443
