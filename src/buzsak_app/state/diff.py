"""Compare two snapshots so views re-render only what changed (UPD-07, ARC-06).

`observed_at` is deliberately ignored: it changes on every poll, even when the value did not,
and freshness is shown by the global "updated N s ago" indicator instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from buzsak_app.domain.models import Device, Parameter, Snapshot

ParameterKey = tuple[str, str]  # (device_id, parameter_id)


@dataclass(frozen=True)
class SnapshotDiff:
    # Parties or devices appeared, disappeared or were reordered: rebuild tabs.
    structure_changed: bool
    # Devices whose health, capabilities, last pulse, label or enabled flag changed.
    changed_devices: frozenset[str]
    # Parameters whose value, state or change time differs.
    changed_parameters: frozenset[ParameterKey]

    @property
    def is_empty(self) -> bool:
        return not (self.structure_changed or self.changed_devices or self.changed_parameters)


def _display_fields(p: Parameter) -> tuple:
    return (p.value, p.state, p.issue, p.unit, p.category, p.last_changed_at, p.revision)


def _device_fields(d: Device) -> tuple:
    return (d.label, d.address, d.enabled, d.health, d.capabilities, d.last_pulse)


def _shape(snapshot: Snapshot) -> tuple:
    return tuple(
        (party.id, party.label, party.configured,
         party.note, tuple(d.id for d in party.devices))
        for party in snapshot.parties
    )


def diff_snapshots(old: Snapshot | None, new: Snapshot) -> SnapshotDiff:
    if old is None:
        devices = [d for party in new.parties for d in party.devices]
        return SnapshotDiff(
            structure_changed=True,
            changed_devices=frozenset(d.id for d in devices),
            changed_parameters=frozenset((d.id, p.id)
                                         for d in devices for p in d.parameters),
        )

    old_devices = {d.id: d for party in old.parties for d in party.devices}
    changed_devices: set[str] = set()
    changed_parameters: set[ParameterKey] = set()
    for party in new.parties:
        for device in party.devices:
            before = old_devices.get(device.id)
            if before is None:
                changed_devices.add(device.id)
                changed_parameters.update((device.id, p.id)
                                          for p in device.parameters)
                continue
            if _device_fields(before) != _device_fields(device):
                changed_devices.add(device.id)
            old_params = {p.id: p for p in before.parameters}
            for parameter in device.parameters:
                previous = old_params.get(parameter.id)
                if previous is None or _display_fields(previous) != _display_fields(parameter):
                    changed_parameters.add((device.id, parameter.id))
            # A removed parameter changes what the device shows.
            if {p.id for p in device.parameters} != set(old_params):
                changed_devices.add(device.id)

    return SnapshotDiff(
        structure_changed=_shape(old) != _shape(new),
        changed_devices=frozenset(changed_devices),
        changed_parameters=frozenset(changed_parameters),
    )
