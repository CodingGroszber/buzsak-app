# Overview Tab

Covers UX-01..UX-03, SSOT-01, UPD-07.

## Content

- One card per configured or placeholder party, in server order.
- Party label, device health, available device details, and headline KPIs selected by `domain/presentation.py`.
- Unknown parties still receive a generic card and tab.

## Behavior

- Selecting a party card navigates to that party's tab.
- The overview is rebuilt when the snapshot changes; party tabs are updated in place.
- Values, quality and health come from the latest server snapshot. The overview contains no actuators.

## Edge cases

- Unconfigured parties show the server note.
- Parties without devices show the no-devices message.
- Missing headline parameters are omitted rather than synthesized as zero or off.
