"""Regression tests for the two different lobby TLS health checks."""
from pathlib import Path
from unittest.mock import patch

from tools import deploy_server


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class TLSContext:
    instances = []

    def __init__(self, protocol):
        self.protocol = protocol
        self.alpn = None
        self.verify_mode = None
        self.check_hostname = None
        self.ca = None
        TLSContext.instances.append(self)

    def load_verify_locations(self, *, cadata):
        self.ca = cadata

    def set_alpn_protocols(self, protocols):
        self.alpn = protocols

    def wrap_socket(self, raw, server_hostname):
        if self.alpn:
            assert self.alpn == ["h2"]
            assert raw.port == 18443
        else:
            assert raw.port == 18444
        assert server_hostname == "mkwom-health"
        assert self.verify_mode == deploy_server.ssl.CERT_REQUIRED
        assert self.ca == b"trusted private CA"
        return Wrapped(self.alpn)


class Wrapped(Connection):
    def __init__(self, alpn):
        self.alpn = alpn

    def selected_alpn_protocol(self):
        return "h2" if self.alpn == ["h2"] else None


class Raw(Connection):
    def __init__(self, port):
        self.port = port


def test_health_checks_http2_and_friends_tls_separately(tmp_path: Path):
    ca = tmp_path / "ca.der"
    ca.write_bytes(b"trusted private CA")
    TLSContext.instances.clear()
    checked = []

    def connect(address, timeout):
        assert timeout == 3
        checked.append(address)
        return Raw(address[1])

    with patch.object(deploy_server.ssl, "SSLContext", TLSContext), \
         patch.object(deploy_server.socket, "create_connection", side_effect=connect):
        deploy_server.health("192.168.0.149", 18443, ca)

    assert checked == [("192.168.0.149", 18443), ("192.168.0.149", 18444)]
    assert [ctx.alpn for ctx in TLSContext.instances] == [["h2"], None]
