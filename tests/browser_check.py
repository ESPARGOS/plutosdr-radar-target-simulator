"""Exercise the UI in an isolated Chromium CDP session (no third-party JS)."""

import base64, json, os, time, urllib.request
from pathlib import Path
import websocket

root = Path(__file__).resolve().parents[1]
base = os.environ.get("RADAR_PREVIEW_URL", "http://127.0.0.1:8080")
debug = "http://localhost:" + os.environ.get("RADAR_BROWSER_DEBUG_PORT", "9223")
tabs = json.load(urllib.request.urlopen(debug + "/json"))
tab = next(
    t for t in tabs if t.get("type") == "page" and not t["url"].startswith("chrome://")
)
w = websocket.create_connection(tab["webSocketDebuggerUrl"], origin=debug)
seq = 0
errors = []


def call(method, params=None):
    global seq
    seq += 1
    w.send(json.dumps({"id": seq, "method": method, "params": params or {}}))
    while True:
        r = json.loads(w.recv())
        if r.get("method") == "Runtime.exceptionThrown":
            errors.append(r)
        if r.get("id") == seq:
            if "error" in r:
                raise RuntimeError(r["error"])
            return r.get("result", {})


def js(expression):
    r = call(
        "Runtime.evaluate",
        dict(expression=expression, returnByValue=True, awaitPromise=True),
    )
    if "exceptionDetails" in r:
        raise RuntimeError(r)
    return r["result"].get("value")


req = urllib.request.Request(
    base + "/api/apply",
    data=b"0\n" + b"0 0 0\n" * 4,
    headers={"Content-Type": "text/plain"},
)
assert json.load(urllib.request.urlopen(req))["mode"] == "demo"
call("Runtime.enable")
call("Page.enable")
call(
    "Emulation.setDeviceMetricsOverride",
    dict(width=1440, height=1100, deviceScaleFactor=1, mobile=False),
)
call("Page.navigate", {"url": base + "/"})
time.sleep(1)
js(
    "(async()=>{globalThis.app=await import('/app.js');globalThis.sceneModel=await import('/scene.js');})()"
)
assert js("document.getElementById('connection').textContent").startswith("Demo"), (
    js(
        "({connection:document.getElementById('connection').textContent,error:app.controller.error,state:app.controller.state,running:app.controller.running})"
    ),
    errors,
)
js(
    "document.getElementById('add').click(); document.getElementById('add').click(); document.getElementById('add').click(); document.getElementById('add').click()"
)
assert js("document.querySelectorAll('.target-summary').length") == 4
assert js("document.getElementById('add').disabled")
time.sleep(0.5)
assert js("app.controller.targets.every(t=>t.enabled)"), "New targets must start On"
js(
    "app.plot.select(0);document.getElementById('range').value=(sceneModel.latency(app.controller.state)+7.123)*sceneModel.METERS_PER_US;document.getElementById('range').dispatchEvent(new Event('change'));document.getElementById('doppler').value=-31.25;document.getElementById('doppler').dispatchEvent(new Event('change'))"
)
time.sleep(0.5)
assert abs(js("app.controller.targets[0].delay_us") - 7.1) < 1e-7
assert js("document.getElementById('enabled').getAttribute('aria-pressed')==='true'")
js("document.getElementById('disabled').click()")
time.sleep(0.3)
assert not js("app.controller.targets[0].enabled")
js("document.getElementById('enabled').click()")
time.sleep(0.3)
before = js("app.controller.targets[0].delay_us")
# Move one target using browser pointer input, then check its changed properties.
box = js(
    "(()=>{const r=document.querySelector('#targets g').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()"
)
call(
    "Input.dispatchMouseEvent",
    dict(type="mousePressed", x=box["x"], y=box["y"], button="left", clickCount=1),
)
call(
    "Input.dispatchMouseEvent",
    dict(
        type="mouseMoved", x=box["x"] + 100, y=box["y"] - 30, button="left", buttons=1
    ),
)
call(
    "Input.dispatchMouseEvent",
    dict(
        type="mouseReleased",
        x=box["x"] + 100,
        y=box["y"] - 30,
        button="left",
        clickCount=1,
    ),
)
time.sleep(0.3)
assert js("app.controller.targets[0].delay_us") > before
time.sleep(0.3)
image = call(
    "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}
)["data"]
(root / "build/ui-desktop.png").write_bytes(base64.b64decode(image))
call(
    "Emulation.setDeviceMetricsOverride",
    dict(width=390, height=844, deviceScaleFactor=1, mobile=True),
)
time.sleep(0.2)
assert js("document.documentElement.scrollWidth <= window.innerWidth")
(root / "build/ui-mobile.png").write_bytes(
    base64.b64decode(
        call(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True}
        )["data"]
    )
)
js("document.getElementById('mute').click()")
time.sleep(0.3)
assert js("app.controller.targets.every(t=>!t.enabled)")
assert not errors, errors
print(
    "PASS: enabled target defaults, joined On/Off, precise edits, automatic quantized apply, pointer drag, mute, mobile width, no browser exceptions"
)
w.close()
