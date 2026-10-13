# Settings Tab

Covers UX-01, UX-04, ARC-09, NTF-01..NTF-13.

Settings follows System and holds server URL, masked bearer token, Save and Sign out. Polling interval and request/command timeouts are fixed constants baked into the release build and are no longer user-editable here. Ordinary preferences exclude the token; Android Keystore persistence is unchanged.

The custom-alert editor normally shows only the saved alert list and a "New alert" button; the creation/edit form is hidden until one is opened. An alert can only be created on a physical, SI-unit telemetry value (booleans, text and unitless fields are not selectable), chosen through a cascaded Location -> Type -> Sensor picker (e.g. Greenhouse -> Temperature -> Sensor A). After the value is picked, a relation (`<`, `<=`, `>`, `>=`, `==`, `!=`) and a numeric limit complete the alert; there is no AND/OR combinator in the editor. Multiple independent alerts can be added in parallel through repeated "New alert" use. Rule definitions persist on this phone only, without runtime truth/cooldown state. Load failure disables editing to avoid overwriting an unreadable saved catalog.

The pure evaluator and persistence are implemented and tested. Runtime connects to the Android delivery/service adapter; the native plugin compiled successfully into an APK on 2026-10-09. Monitoring status reports stopped, active, denied permission, unavailable or timeout. Physical-device background/delivery acceptance remains B-504/B-505; a successful build is not device execution proof. No alert rule actuates hardware or requires Pi changes.