"""Is a store reachable? Used before refreshing, signing in or downloading, and to explain network failures."""
from __future__ import annotations



STORE_HOSTS = {"booth": "accounts.booth.pm", "gumroad": "app.gumroad.com", "jinxxy": "jinxxy.com", "payhip": "payhip.com",
               "itch": "itch.io"}


NETWORK_ERRORS = ("ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_NAME_RESOLUTION_FAILED",
                  "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT",
                  "ERR_NETWORK_CHANGED", "ERR_ADDRESS_UNREACHABLE", "ERR_PROXY_CONNECTION_FAILED",
                  "getaddrinfo", "Name or service not known", "Temporary failure in name resolution",
                  "Failed to establish a new connection", "Max retries exceeded")


def reachable(store: str, timeout: float = 5.0) -> bool:
    """True when a connection to the store's website can be opened right now."""
    import socket
    try:
        with socket.create_connection((STORE_HOSTS[store], 443), timeout=timeout):
            return True
    except OSError:
        return False


def is_network_error(error: Exception) -> bool:
    """True when an error means the store couldn't be reached, rather than something going wrong on it."""
    return any(code in str(error) for code in NETWORK_ERRORS)
