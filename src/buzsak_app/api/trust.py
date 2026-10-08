"""Pinned trust anchor for the Buzsák server's HTTPS (SEC-02, SEC-03, ADR-0003).

The server's Caddy `tls internal` CA is a private root, so the public web CAs and the Android
system store cannot vouch for it. Only this public certificate is trusted for HTTPS: no other
server is accepted. If Caddy's CA is regenerated, replace the PEM below and rebuild the app.
"""

from __future__ import annotations

import ssl

# Public certificate (not a secret). Source: the server's `.tmp/caddy-root.crt`.
SERVER_ROOT_CA_PEM = """\
-----BEGIN CERTIFICATE-----
MIIBpDCCAUmgAwIBAgIQJ/5DOmaycUstmKJ/qMBI6TAKBggqhkjOPQQDAjAwMS4w
LAYDVQQDEyVDYWRkeSBMb2NhbCBBdXRob3JpdHkgLSAyMDI2IEVDQyBSb290MB4X
DTI2MTAwNzEwNDIwNVoXDTM2MDgxNTEwNDIwNVowMDEuMCwGA1UEAxMlQ2FkZHkg
TG9jYWwgQXV0aG9yaXR5IC0gMjAyNiBFQ0MgUm9vdDBZMBMGByqGSM49AgEGCCqG
SM49AwEHA0IABME+a4GF59VYt8LyGkBe6oiBw99SC5f2t6+Hkv5YptxXMqVlEDmG
Fe5Lfr9xqU6VA14rNjArhPU4ETGxvJubM3CjRTBDMA4GA1UdDwEB/wQEAwIBBjAS
BgNVHRMBAf8ECDAGAQH/AgEBMB0GA1UdDgQWBBS7fkOX5AR/2/8/oS20NmNFTH+/
rDAKBggqhkjOPQQDAgNJADBGAiEA75FpyNRO1Yb0EZXIEG26eoCiibyydu33L3Jc
z57bOHYCIQCY+ulKQHn206+3d18sH3daF3WJKA0XYML5AvkIoxlWAg==
-----END CERTIFICATE-----
"""


def server_ssl_context() -> ssl.SSLContext:
    """TLS context that verifies the server certificate against the pinned CA only."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=SERVER_ROOT_CA_PEM)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
