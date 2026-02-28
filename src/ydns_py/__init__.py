"""Unofficial YDNS dynamic DNS updater.

Updates A (IPv4) and/or AAAA (IPv6) records via YDNS update URLs.

Config file format (TOML):

  # Both IPv4 and IPv6 addresses
  [[domains]]
  domain = "example.ydns.eu"
  update_url = "https://ydns.io/hosts/update/Wh4tAL0velYDayforS0meDNS"
  update_url_v6 = "https://ydns.io/hosts/update/Wh4tAL0velYDayforIPv6ing"

  # IPv4 address only
  [[domains]]
  domain = "example2.ydns.eu"
  update_url = "https://ydns.io/hosts/update/AL0ngRand0mString1sHeree"

All update URLs are always processed, even if one or more preceding ones did
not complete successfully.

By default, these config files are looked for, in descending priority:

  ~/.config/ydns-py/config.toml
  /etc/ydns-py.toml

Exit codes:
  0  Success. In lax mode (default), non-2xx HTTP responses do not affect this.
  1  Config file not found.
  2  Config file could not be parsed.
  3  Config file contains no [[domains]] entries.
  4  One or more updates returned non-2xx HTTP responses (strict mode only).
  5  One or more connection errors occurred.
"""

import argparse
import http.client
import socket
import sys
import tomllib
import urllib.error
import urllib.request
from enum import Enum, auto
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    __version__ = version("ydns-py")
except PackageNotFoundError:
    __version__ = "unknown"

EX_CONFIG_NOT_FOUND = 1
EX_CONFIG_PARSE_ERROR = 2
EX_NO_DOMAINS = 3
EX_UPDATE_FAILED = 4
EX_CONNECTION_ERROR = 5

DEFAULT_CONFIG_PATHS = [
    Path("~/.config/ydns-py/config.toml").expanduser(),
    Path("/etc/ydns-py.toml"),
]

TIMEOUT = 5  # seconds


class _ForcedAFHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection restricted to a specific address family."""

    _address_family: socket.AddressFamily = socket.AF_UNSPEC

    def connect(self) -> None:
        port = self.port or http.client.HTTPS_PORT
        infos = socket.getaddrinfo(self.host, port, self._address_family, socket.SOCK_STREAM)
        if not infos:
            raise OSError(
                f"getaddrinfo returned no results for {self.host!r} in address family {self._address_family.name}"
            )
        af, socktype, proto, _, sa = infos[0]
        sock = socket.socket(af, socktype, proto)
        sock.settimeout(self.timeout)
        try:
            sock.connect(sa)
        except BaseException:
            sock.close()
            raise
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self._tunnel_host)
        else:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _IPv4HTTPSConnection(_ForcedAFHTTPSConnection):
    _address_family = socket.AF_INET


class _IPv6HTTPSConnection(_ForcedAFHTTPSConnection):
    _address_family = socket.AF_INET6


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_IPv4HTTPSConnection, req, context=self._context)


class _IPv6HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_IPv6HTTPSConnection, req, context=self._context)


class _Result(Enum):
    OK = auto()
    HTTP_ERROR = auto()
    CONN_ERROR = auto()


def _make_opener(ipv6: bool) -> urllib.request.OpenerDirector:
    handler = _IPv6HTTPSHandler() if ipv6 else _IPv4HTTPSHandler()
    return urllib.request.build_opener(handler)


def _update(
    opener: urllib.request.OpenerDirector,
    url: str,
    domain: str,
    label: str,
    verbose: bool,
) -> _Result:
    req = urllib.request.Request(url, headers={"User-Agent": f"ydns-py/{__version__}"})
    status: int | None = None
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        print(f"{domain} ({label}): connection error: {e}", file=sys.stderr)
        return _Result.CONN_ERROR

    if 200 <= status < 300:
        if verbose:
            print(f"Updated {domain} ({label}) successfully.")
        return _Result.OK
    elif status == 404:
        print(
            f"{domain} ({label}): update URL is invalid (404). Check your configuration.",
            file=sys.stderr,
        )
    elif status == 400:
        print(
            f"{domain} ({label}): server rejected the request (400). You may not have a public {label} address.",
            file=sys.stderr,
        )
    else:
        print(
            f"{domain} ({label}): unexpected HTTP status {status}.",
            file=sys.stderr,
        )
    return _Result.HTTP_ERROR


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YDNS dynamic DNS record updater.",
    )
    parser.add_argument("-c", "--config", metavar="FILE", help="Path to config file.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log each successful update to stdout (silent by default)",
    )
    parser.add_argument(
        "-s",
        "--strict",
        action="store_true",
        help="Individual update failures will cause an exit with code 4 instead of 0",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Config file not found: {config_path}", file=sys.stderr)
            sys.exit(EX_CONFIG_NOT_FOUND)
    else:
        for path in DEFAULT_CONFIG_PATHS:
            if path.exists():
                config_path = path
                break
        else:
            searched = ", ".join(str(p) for p in DEFAULT_CONFIG_PATHS)
            print(
                f"Config file not found (searched: {searched})",
                file=sys.stderr,
            )
            sys.exit(EX_CONFIG_NOT_FOUND)

    try:
        with Path.open(config_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        print(f"Failed to read {config_path}: {e}", file=sys.stderr)
        sys.exit(EX_CONFIG_PARSE_ERROR)

    domains = config.get("domains", [])
    if not domains:
        print(
            f"No [[domains]] entries found in {config_path}",
            file=sys.stderr,
        )
        sys.exit(EX_NO_DOMAINS)

    ipv4_opener = _make_opener(ipv6=False)
    ipv6_opener = _make_opener(ipv6=True)
    any_http_error = False
    any_conn_error = False

    for entry in domains:
        domain = entry.get("domain", "<undefined>")
        update_url = entry.get("update_url")
        if update_url:
            result = _update(ipv4_opener, update_url, domain, "IPv4", args.verbose)
            if result == _Result.HTTP_ERROR:
                any_http_error = True
            elif result == _Result.CONN_ERROR:
                any_conn_error = True

        update_url_v6 = entry.get("update_url_v6")
        if update_url_v6:
            result = _update(ipv6_opener, update_url_v6, domain, "IPv6", args.verbose)
            if result == _Result.HTTP_ERROR:
                any_http_error = True
            elif result == _Result.CONN_ERROR:
                any_conn_error = True

        if not update_url and not update_url_v6:
            print(
                f"No update URLs configured for {domain}, updates not attempted",
                file=sys.stderr,
            )

    if any_conn_error:
        sys.exit(EX_CONNECTION_ERROR)
    if args.strict and any_http_error:
        sys.exit(EX_UPDATE_FAILED)
