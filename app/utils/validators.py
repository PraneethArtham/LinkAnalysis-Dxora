"""URL validation and SSRF protection utilities."""

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException


# Schemes that are explicitly blocked
BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript", "telnet", "ssh"}

# Private and reserved IP ranges (SSRF protection)
PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 private ranges
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address belongs to a private or reserved range.

    Args:
        ip_str: IP address string to check.

    Returns:
        True if the IP is private/reserved, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in PRIVATE_NETWORKS)
    except ValueError:
        return True  # If we can't parse it, block it for safety


def validate_url(url: str) -> str:
    """Validate URL format and check for SSRF vulnerabilities.

    Args:
        url: The URL string to validate.

    Returns:
        The validated URL string.

    Raises:
        HTTPException: If the URL is invalid or poses SSRF risk.
    """
    # Basic format check
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # Check scheme
    if not parsed.scheme:
        raise HTTPException(
            status_code=400,
            detail="URL must include a scheme (http:// or https://)",
        )

    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme '{scheme}' is not allowed",
        )

    if scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported URL scheme: {scheme}. Only HTTP and HTTPS are allowed.",
        )

    # Check hostname exists
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="URL must include a valid hostname")

    # Block common localhost variations
    blocked_hosts = {"localhost", "0.0.0.0", "[::]", "[::1]"}
    if hostname.lower() in blocked_hosts:
        raise HTTPException(
            status_code=400, detail="Access to localhost/loopback addresses is not allowed"
        )

    # Resolve hostname and verify resolved IPs are not private
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not resolved:
            raise HTTPException(
                status_code=400, detail=f"Could not resolve hostname: {hostname}"
            )

        for _, _, _, _, sockaddr in resolved:
            ip_str = sockaddr[0]
            if is_private_ip(ip_str):
                raise HTTPException(
                    status_code=400,
                    detail="Access to private or internal network addresses is not allowed (SSRF protection)",
                )
    except socket.gaierror:
        raise HTTPException(
            status_code=400, detail=f"Could not resolve hostname: {hostname}"
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"URL validation failed: {str(exc)}"
        )

    return url
