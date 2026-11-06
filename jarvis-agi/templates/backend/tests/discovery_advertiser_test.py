from pathlib import Path

import app.discovery as discovery
from app.config import Settings
from app.discovery import GatewayAdvertiser


class FakeZeroconf:
    instances: list["FakeZeroconf"] = []

    def __init__(self):
        self.registered = None
        self.unregistered = None
        self.closed = False
        self.instances.append(self)

    def register_service(self, service, allow_name_change: bool = False):
        self.registered = (service, allow_name_change)

    def unregister_service(self, service):
        self.unregistered = service

    def close(self):
        self.closed = True


def configured_settings() -> Settings:
    return Settings(
        pairing_code="pairing-code-for-test",
        token_secret="token-secret-for-test",
        data_dir=Path("/tmp/discovery-advertiser-test"),
        local_ollama_enabled=False,
        local_ollama_base_url="http://127.0.0.1:11434/v1",
        local_ollama_model="test-model",
        cloud_fallback_enabled=False,
        deepseek_api_key="",
        deepseek_base_url="https://api.example.com",
        deepseek_model="test-model",
        gateway_discovery_enabled=True,
        gateway_discovery_name="Lab Gateway",
        gateway_discovery_url="https://gateway.example.test:8443",
        gateway_discovery_address="192.168.20.10",
    )


original = discovery.Zeroconf
discovery.Zeroconf = FakeZeroconf
try:
    advertiser = GatewayAdvertiser(configured_settings())
    advertiser.start()
    instance = FakeZeroconf.instances[-1]
    service, allow_name_change = instance.registered
    assert allow_name_change is True
    assert service.properties[b"url"] == b"https://gateway.example.test:8443"
    assert service.port == 8443
    advertiser.stop()
    assert instance.unregistered is service
    assert instance.closed is True
finally:
    discovery.Zeroconf = original

print("discovery advertiser test passed")
