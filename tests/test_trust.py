"""The pinned server CA: only that certificate is trusted (SEC-02, ADR-0003)."""

from __future__ import annotations

import ssl

from buzsak_app.api.trust import SERVER_ROOT_CA_PEM, server_ssl_context


def test_only_the_pinned_ca_is_trusted() -> None:
    certificates = server_ssl_context().get_ca_certs()
    assert len(certificates) == 1
    subject = dict(item[0] for item in certificates[0]["subject"])
    assert "Caddy Local Authority" in subject["commonName"]


def test_server_certificates_and_hostnames_are_verified() -> None:
    context = server_ssl_context()
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_the_embedded_pem_is_a_public_certificate_only() -> None:
    assert SERVER_ROOT_CA_PEM.count("BEGIN CERTIFICATE") == 1
    assert "PRIVATE KEY" not in SERVER_ROOT_CA_PEM
