"""Is the server's data itself old, even though the server answers? (DATA-02, UPD-06)

"Online, updated 0 s ago" only says the HTTP request worked. If the server's poller has stopped,
every parameter turns stale while the connection looks fine, and the user must be told.
Both timestamps come from the server, so clock skew between phone and Pi cannot distort the age.
"""

from __future__ import annotations

from buzsak_app.domain.models import Snapshot, ValueState


def stale_server_data_age_s(snapshot: Snapshot | None) -> float | None:
    """Age in seconds of the newest observation if every observed parameter is stale, else None.

    None also covers "nothing observed yet" and mixed states: per-device health and the
    per-parameter badges already describe those.
    """
    if snapshot is None:
        return None
    observed = [
        p
        for party in snapshot.parties
        for device in party.devices
        for p in device.parameters
        if p.state is not ValueState.NO_DATA
    ]
    if not observed or any(p.state is not ValueState.STALE for p in observed):
        return None
    newest = max(
        (p.observed_at for p in observed if p.observed_at is not None), default=None)
    if newest is None:
        return None
    return max(0.0, (snapshot.generated_at - newest).total_seconds())
