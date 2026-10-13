"""Phone-local flat numeric rule editor (NTF-01, NTF-02, NTF-05, NTF-06)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import flet as ft

from buzsak_app.domain.alerts import (
    AlertRule, Comparison, Constant, ValueReference, selectable_parameter,
)
from buzsak_app.domain.models import Snapshot
from buzsak_app.ui import strings
from buzsak_app.ui.components import muted_text, section_title
from buzsak_app.ui.theme import SPACING

SaveRules = Callable[[tuple[AlertRule, ...]], Awaitable[bool]]

# location label -> type label -> reference keys sharing that party and physical unit.
Tree = dict[str, dict[str, list[str]]]

_RELATIONS = ("<", "<=", ">", ">=", "==", "!=")


class _ValuePicker:
    """Cascaded Location -> Type -> Sensor picker, plus relation and constant (NTF-02, NTF-06)."""

    def __init__(self, owner: AlertEditor) -> None:
        self.owner = owner
        self.location = ft.Dropdown(
            label=strings.ALERT_LOCATION, on_select=self._location_changed)
        self.category = ft.Dropdown(
            label=strings.ALERT_TYPE, visible=False, on_select=self._category_changed)
        self.sensor = ft.Dropdown(
            label=strings.ALERT_SENSOR, visible=False, on_select=self._sensor_changed)
        self.relation = ft.Dropdown(
            label=strings.ALERT_RELATION, value=">=", visible=False, width=110,
            options=[ft.DropdownOption(key=value, text=value)
                     for value in _RELATIONS],
        )
        self.constant = ft.TextField(
            label=strings.ALERT_NUMBER, visible=False, expand=True)
        self._relation_row = ft.Row(
            [self.relation, self.constant], spacing=SPACING.sm)
        self.control = ft.Column([
            self.location, self.category, self.sensor, self._relation_row,
        ], spacing=SPACING.sm)

    def _location_options(self) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=label, text=label)
                for label in sorted(self.owner.tree)]

    def _populate_category(self, *, keep_value: bool) -> None:
        categories = self.owner.tree.get(self.location.value or "", {})
        self.category.options = [ft.DropdownOption(key=label, text=label)
                                 for label in sorted(categories)]
        self.category.visible = bool(categories)
        if not keep_value or self.category.value not in categories:
            self.category.value = None

    def _populate_sensor(self, *, keep_value: bool) -> None:
        keys = self.owner.tree.get(self.location.value or "", {}).get(
            self.category.value or "", [])
        if len(keys) > 1:
            self.sensor.visible = True
            self.sensor.options = [ft.DropdownOption(
                key=key, text=self.owner.labels.get(key, key)) for key in keys]
            if not keep_value or self.sensor.value not in keys:
                self.sensor.value = None
        else:
            self.sensor.visible = False
            self.sensor.options = []
            self.sensor.value = None
        self.relation.visible = bool(keys)
        self.constant.visible = bool(keys)

    def refresh_options(self) -> None:
        self.location.options = self._location_options()
        if self.location.value in self.owner.tree:
            self._populate_category(keep_value=True)
        if self.category.visible and self.category.value:
            self._populate_sensor(keep_value=True)

    def _location_changed(self, _: ft.Event) -> None:
        self._populate_category(keep_value=False)
        self.sensor.visible = False
        self.sensor.options = []
        self.relation.visible = False
        self.constant.visible = False
        self.owner.update()

    def _category_changed(self, _: ft.Event) -> None:
        self._populate_sensor(keep_value=False)
        self.owner.update()

    def _sensor_changed(self, _: ft.Event) -> None:
        self.owner.update()

    def reset(self) -> None:
        self.location.value = None
        self.location.options = self._location_options()
        self.category.value = None
        self.category.options = []
        self.category.visible = False
        self.sensor.value = None
        self.sensor.options = []
        self.sensor.visible = False
        self.relation.value = ">="
        self.relation.visible = False
        self.constant.value = ""
        self.constant.visible = False

    def current_key(self) -> str | None:
        keys = self.owner.tree.get(self.location.value or "", {}).get(
            self.category.value or "", [])
        if len(keys) == 1:
            return keys[0]
        return self.sensor.value if self.sensor.value in keys else None

    def load(self, comparison: Comparison) -> None:
        reference = comparison.left
        if not isinstance(reference, ValueReference):
            return
        key = self.owner.reference_key(reference)
        self.owner.references.setdefault(key, reference)
        self.location.value = self.owner.party_of.get(
            reference.device_id, reference.device_id)
        self._populate_category(keep_value=False)
        self.category.value = strings.unit_category_label(reference.unit)
        self._populate_sensor(keep_value=False)
        if self.sensor.visible:
            self.sensor.value = key
        self.relation.value = comparison.relation
        self.relation.visible = True
        self.constant.value = (
            str(comparison.right.value) if isinstance(comparison.right, Constant) else "")
        self.constant.visible = True

    def value(self) -> Comparison:
        key = self.current_key()
        if key is None or key not in self.owner.references:
            raise ValueError("telemetry value required")
        reference = self.owner.references[key]
        relation = self.relation.value or ""
        try:
            constant = float(self.constant.value or "")
        except ValueError as error:
            raise ValueError("numeric limit required") from error
        return Comparison(reference, relation, Constant(constant, reference.unit))


class AlertEditor:
    def __init__(self, *, on_save: SaveRules, page: ft.Page | None = None) -> None:
        self._page = page
        self._on_save = on_save
        self.rules: tuple[AlertRule, ...] = ()
        self.references: dict[str, ValueReference] = {}
        self.labels: dict[str, str] = {}
        self.party_of: dict[str, str] = {}
        self.tree: Tree = {}
        self.editing_id: str | None = None
        self.name = ft.TextField(label=strings.ALERT_NAME)
        self.picker = _ValuePicker(self)
        self.message = muted_text()
        self.status = muted_text(strings.ALERT_MONITOR_STOPPED)
        self._list = ft.Column(spacing=SPACING.sm)
        self._list_container = ft.Column([
            self._list,
            ft.TextButton(strings.ALERT_NEW, on_click=self.new),
        ], spacing=SPACING.sm)
        self._form_container = ft.Column([
            self.name, self.picker.control,
            ft.Row([
                ft.FilledButton(strings.SYSTEM_SAVE, on_click=self.save),
                ft.TextButton(strings.ALERT_CANCEL, on_click=self.cancel),
            ], wrap=True), self.message,
        ], spacing=SPACING.sm, visible=False)
        self.control = ft.Column([
            section_title(strings.ALERTS_TITLE), self.status,
            self._list_container, self._form_container,
        ], spacing=SPACING.sm)

    @staticmethod
    def reference_key(reference: ValueReference) -> str:
        import json
        return json.dumps([reference.device_id, reference.parameter_id, reference.unit])

    def update(self) -> None:
        if self._page is not None:
            self._page.update()

    def refresh(self, snapshot: Snapshot | None) -> None:
        if snapshot is None:
            return
        for party in snapshot.parties:
            for device in party.devices:
                self.party_of[device.id] = party.label
                for parameter in device.parameters:
                    if selectable_parameter(parameter):
                        reference = ValueReference(
                            device.id, parameter.id, parameter.unit)
                        key = self.reference_key(reference)
                        self.references[key] = reference
                        self.labels[
                            key] = f"{strings.parameter_label(parameter.id)} ({parameter.unit})"
        tree: Tree = {}
        for key, reference in self.references.items():
            location = self.party_of.get(
                reference.device_id, reference.device_id)
            category = strings.unit_category_label(reference.unit)
            tree.setdefault(location, {}).setdefault(category, []).append(key)
        if tree != self.tree:
            self.tree = tree
            self.picker.refresh_options()

    def set_rules(self, rules: tuple[AlertRule, ...]) -> None:
        self.rules = rules
        self._list.controls = []
        for rule in rules:
            async def remove(_: ft.Event, rule_id=rule.id) -> None:
                updated = tuple(
                    item for item in self.rules if item.id != rule_id)
                if await self._on_save(updated):
                    self.set_rules(updated)
                    if self.editing_id == rule_id:
                        self._show_list()
                else:
                    self.message.value = strings.ALERT_STORAGE_ERROR
                self.update()

            def edit(_: ft.Event, selected=rule) -> None:
                self.editing_id = selected.id
                self.name.value = selected.name
                self.picker.load(selected.comparisons[0])
                self.message.value = ""
                self._show_form()

            self._list.controls.append(ft.Row([
                ft.Text(rule.name, expand=True),
                ft.IconButton(icon=ft.Icons.EDIT,
                              tooltip=strings.ALERT_EDIT, on_click=edit),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE,
                              tooltip=strings.ALERT_DELETE, on_click=remove),
            ]))

    def _show_form(self) -> None:
        self._list_container.visible = False
        self._form_container.visible = True
        self.update()

    def _show_list(self) -> None:
        self._form_container.visible = False
        self._list_container.visible = True
        self.update()

    def new(self, _: ft.Event) -> None:
        self.editing_id = None
        self.name.value = ""
        self.message.value = ""
        self.picker.reset()
        self._show_form()

    def cancel(self, _: ft.Event) -> None:
        self.message.value = ""
        self._show_list()

    async def save(self, _: ft.Event) -> None:
        try:
            rule = AlertRule(
                self.editing_id or str(uuid.uuid4()),
                (self.name.value or "").strip(),
                (self.picker.value(),), "AND",
            )
        except (ValueError, TypeError):
            self.message.value = strings.ALERT_INVALID
            self.update()
            return
        updated = tuple(rule if item.id ==
                        rule.id else item for item in self.rules)
        if not any(item.id == rule.id for item in self.rules):
            updated += (rule,)
        if await self._on_save(updated):
            self.set_rules(updated)
            self.message.value = strings.SYSTEM_SAVED
            self._show_list()
        else:
            self.message.value = strings.ALERT_STORAGE_ERROR
        self.update()
