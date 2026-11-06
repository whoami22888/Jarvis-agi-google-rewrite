from app.discovery import _validated_gateway_url


assert _validated_gateway_url("https://gateway.example.com") == ("https://gateway.example.com", 443)
assert _validated_gateway_url("https://gateway.example.com:8443/path/") == ("https://gateway.example.com:8443/path", 8443)

for invalid in (
    "",
    "http://gateway.example.com",
    "https://user:password@gateway.example.com",
    "https://gateway.example.com/?token=not-allowed",
    "https://gateway.example.com/#fragment",
):
    try:
        _validated_gateway_url(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Expected invalid discovery URL to be rejected: {invalid}")

print("discovery validation test passed")
