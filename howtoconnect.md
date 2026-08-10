# How To Connect

This file is only about how users can reach the dashboard and verify it works.

## Quick URLs

- LAN primary: http://192.168.1.95
- LAN direct app port: http://192.168.1.95:8550
- Matter server (operator check): http://192.168.1.95:5580
- Tailscale tailnet IP: http://100.123.208.10

## User Type A: Family User On Home Wi-Fi

1. Open http://192.168.1.95
2. If it opens, access is OK.
3. If it fails, try http://192.168.1.95:8550
4. If 8550 works but 80 does not, nginx/proxy issue. Tell operator.

## User Type B: Remote User With Tailscale

1. Confirm Tailscale is connected on your device.
2. Open http://100.123.208.10
3. If it fails, check your device can ping the Pi tailnet IP.
4. If still failing, operator should verify tailscaled on Pi and ACL/routing in tailnet.

## User Type C: Operator Or Developer (SSH Access)

1. SSH to Pi.
2. Run:

```bash
bash /home/neulas/projects/py_app/ops/pi/statuscheck_remote.sh
```

3. Confirm these checks are green:
- HTTP/1.1 200 OK on 127.0.0.1:8550
- HTTP/1.1 200 OK on 127.0.0.1
- No failed units
- Ports listening: 80, 8550, 5580

4. For deploy status and recent changes on Pi:

```bash
cd /home/neulas/projects/py_app
git status -sb
git log --oneline -n 8
```

5. For service logs after a deploy or config change:

```bash
sudo journalctl -u py-app-dashboard.service -n 200 --no-pager
```

## Matter Server Page (What To Expect)

- Open http://192.168.1.95:5580 for a quick reachability check.
- This is not the dashboard UI. Matter control is via websocket.
- Dashboard now tries both websocket addresses: `ws://127.0.0.1:5580/ws` first, then `ws://192.168.1.95:5580/ws` as fallback.
- If port 5580 is reachable but doors are offline on dashboard, issue is usually node availability, node ID mapping, or endpoint mismatch.

## Matter Node Availability Check

When dashboard shows Matter offline, server may still be up while door nodes are unavailable.

Run this quick check:

```bash
cd /home/neulas/projects/py_app
source .venv/bin/activate
python - <<"PY"
import json, websocket
for node in (1, 3):
    ws = websocket.create_connection("ws://127.0.0.1:5580/ws", timeout=4)
    ws.recv()
    ws.send(json.dumps({
        "message_id": "1",
        "command": "read_attribute",
        "args": {"node_id": node, "attribute_path": "1/6/0"}
    }))
    print(node, ws.recv())
    ws.close()
PY
```

Interpretation:
- If response says Node is not yet available, Matter server is online but the device node is not currently reachable.
- If websocket connection itself fails, Matter server/service is down.

## Matter Endpoint And Node-ID Diagnostic (Garage Openers Offline)

Your dashboard uses these fixed values from `main.py`:
- Node IDs: 1 (right), 3 (left)
- Endpoint ID: 1
- Cluster: 6 (OnOff)
- Attribute path: `1/6/0`

If Sonoff relays were re-paired/re-commissioned, those values can drift. Run this probe on Pi:

```bash
cd /home/neulas/projects/py_app
source .venv/bin/activate
python - <<"PY"
import json
import websocket

WS_URL = "ws://127.0.0.1:5580/ws"
node_ids = (1, 3)
endpoints = (0, 1, 2)

for node in node_ids:
    print(f"\\nnode {node}")
    for ep in endpoints:
        ws = websocket.create_connection(WS_URL, timeout=4)
        try:
            ws.recv()
            ws.send(json.dumps({
                "message_id": "1",
                "command": "read_attribute",
                "args": {"node_id": node, "attribute_path": f"{ep}/6/0"},
            }))
            print(f"  ep {ep}: {ws.recv()}")
        except Exception as ex:
            print(f"  ep {ep}: ERROR {ex}")
        finally:
            ws.close()
PY
```

How to read results:
- Connect fails on all checks: matter-server is down or not listening on 5580.
- `not (yet) available`: Matter server is up, but that node is not currently reachable in its fabric.
- Endpoint 0 or 2 works, but endpoint 1 fails: change `MATTER_ENDPOINT_ID` in `main.py` to the working endpoint and redeploy.
- Node 1/3 fail, but another known node works: update `MATTER_DOORS` node IDs in `main.py`.

For live error confirmation during dashboard polling:

```bash
sudo journalctl -u py-app-dashboard.service -n 300 --no-pager | egrep -i 'matter|error|not \(yet\) available'
```

## Fast User Self-Check

Any user can do this without SSH:

1. Open http://192.168.1.95
2. If dashboard loads and updates badges, core access works.
3. If door tiles show offline but page loads, network path is good and issue is on Matter/device side.
