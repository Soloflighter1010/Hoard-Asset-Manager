"""Is a store reachable? Used before refreshing, signing in or downloading, and to explain network failures."""
from __future__ import annotations



STORE_HOSTS = {"booth": "accounts.booth.pm", "gumroad": "app.gumroad.com", "jinxxy": "jinxxy.com", "payhip": "payhip.com",
               "itch": "api.itch.io"}


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


# Why a page didn't load, in plain words: the browser's own name for it, with the address and a log of each step,
# meant little in Stores ("Page.goto: net::ERR_TOO_MANY_REDIRECTS at https://... Call log: - navigating to ...").
PAGE_ERRORS = (
    ("ERR_TOO_MANY_REDIRECTS", "the website kept redirecting in a loop, which is usually a passing problem on the "
                               "website's side"),
    ("ERR_NAME_NOT_RESOLVED", "no website was found at that address"),
    ("ERR_CERT_", "the website's security certificate isn't valid"),
    ("ERR_SSL_", "a secure connection to the website couldn't be made"),
    ("ERR_CONNECTION_", "the website didn't answer"),
    ("ERR_EMPTY_RESPONSE", "the website sent back nothing"),
)


def plain_error(error: Exception) -> str:
    """Why a page couldn't be read, to show you: in plain words where it's one the browser names, else the error's
    first line, without the browser's log of each step."""
    text = str(error)
    for code, words in PAGE_ERRORS:
        if code in text:
            return words
    first = text.strip().split("\n", 1)[0].split(" Call log:", 1)[0].strip()
    if type(error).__name__ == "TimeoutError" or first.startswith("Timeout "):
        return "the website didn't answer in time"
    return first[:300] or type(error).__name__
