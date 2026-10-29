"""Live Pluto CGI and browser check; leaves targets muted."""

import base64, json, os, time, urllib.request, urllib.error, urllib.parse
from pathlib import Path
import websocket

root = Path(__file__).resolve().parents[1]
base = os.environ.get("PLUTO_URL", "http://192.168.4.1").rstrip("/")


def request(path, data=None, origin=None):
    headers = {"Content-Type": "text/plain"}
    if origin:
        headers["Origin"] = origin
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(
                base + "/cgi-bin/radar.cgi/" + path, data=data, headers=headers
            ),
            timeout=6,
        )
        return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


assert request("apply", b"15\n-1 0 1")[0] == 400
assert request("apply", b"15\n" + b"2048 0 1\n" * 4)[0] == 400
assert request("mute", b"", origin="http://example.invalid")[0] == 403
assert request("radio", b"100000000")[0] == 400
assert request("radio", b"2380000000garbage")[0] == 400
initial_radio = request("state")[1]
assert initial_radio["connected"]
assert abs(initial_radio["sample_rate_hz"] - 160000000) <= 100, initial_radio
assert initial_radio.get("hardware_latency_us") == 0.325, initial_radio
for payload in (
    b"rx nan",
    b"tx inf",
    b"rx 30.5",
    b"tx -0.2",
    b"rx 9999",
    b"tx -100",
    b"tx -30 extra",
    b"bad 5",
):
    assert request("gain", payload)[0] == 400, payload
assert request("gain", b"tx -35", origin="http://example.invalid")[0] == 403
debug_origin = "http://localhost:" + os.environ.get("RADAR_BROWSER_DEBUG_PORT", "9223")
tabs = json.load(urllib.request.urlopen(debug_origin + "/json"))
tab = next(
    t for t in tabs if t.get("type") == "page" and not t["url"].startswith("chrome://")
)
w = websocket.create_connection(tab["webSocketDebuggerUrl"], origin=debug_origin)
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


try:
    call("Runtime.enable")
    call("Page.enable")
    call("Network.enable")
    call("Network.setCacheDisabled", {"cacheDisabled": True})
    call(
        "Emulation.setDeviceMetricsOverride",
        dict(width=1920, height=900, deviceScaleFactor=1, mobile=False),
    )
    call("Page.navigate", {"url": base + "/"})
    for _ in range(60):
        if js(
            "(async()=>{if(!window.RADAR_DEVICE||document.readyState!=='complete')return false;globalThis.app=await import('/app.js');globalThis.sceneModel=await import('/scene.js');return app.controller.state?.connected;})()"
        ):
            break
        time.sleep(0.25)
    assert js("window.RADAR_DEVICE && app.controller.state.connected")
    js(
        "app.controller.error='Radar startup is in progress or the FPGA is not loaded';app.controller.notify()"
    )
    assert (
        js("document.getElementById('connection').textContent")
        == "Radar startup is in progress or the FPGA is not loaded"
    )
    assert js(
        "document.querySelector('header').contains(document.getElementById('connection')) && !document.getElementById('feedback')"
    )
    js("app.controller.error='';app.controller.notify()")
    known_latency = initial_radio.get("hardware_latency_us") is not None
    assert js(
        "document.getElementById('fit').form===null && document.getElementById('rx-gain').form===null"
    )
    assert js("!document.getElementById('live') && !document.getElementById('apply')")
    assert js(
        "document.getElementById('sample-rate').textContent.includes(String(app.controller.state.sample_rate_hz/1e6))"
    )
    assert js(
        "document.getElementById('bandwidth').textContent.includes('Analog bandwidth 20 MHz')"
    )
    assert js("document.getElementById('range-axis-title').textContent") == (
        "Total range (m)" if known_latency else "Range offset (m)"
    )
    assert js(
        "[...document.querySelectorAll('.axis-title')].some(x=>x.textContent.trim()==='Radial velocity (m/s)')"
    )
    assert js("document.querySelector('link[rel=icon]').href.endsWith('/favicon.ico')")
    assert (
        urllib.request.urlopen(base + "/favicon.ico").read()
        == (root / "web/favicon.ico").read_bytes()
    )
    assert js("document.querySelector('.brand img').naturalWidth") > 0
    scene = json.loads((root / "config/four-targets.json").read_text())
    js(
        "app.controller.targets="
        + json.dumps(scene["targets"])
        + "; app.controller.selected=0; app.controller.revision++; app.renderEditor(); app.plot.draw();"
    )
    # Small windows may hide targets, but never move velocity zero away from center.
    js(
        "app.plot.setWindow('range',65);app.plot.setWindow('velocity',.25);app.plot.draw()"
    )
    assert js(
        "app.plot.point({delay_us:0,doppler_hz:0}).x===app.plot.geometry().centerX"
    )
    assert js("document.querySelectorAll('.outside').length>0")
    js("document.querySelectorAll('.target-summary')[3].click()")
    assert js(
        "app.plot.inView(app.controller.targets[3]) && app.plot.point({delay_us:0,doppler_hz:0}).x===app.plot.geometry().centerX"
    )
    assert (
        js("sceneModel.totalRange({delay_us:0},app.controller.state)")
        == (initial_radio.get("hardware_latency_us") or 0) * 149.896229
    )
    assert js("document.querySelectorAll('#unavailable-range rect').length") == (
        2 if known_latency else 0
    )
    if known_latency:
        assert js(
            "app.plot.position((()=>{const p=new DOMPoint(app.plot.geometry().centerX,app.plot.geometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {clientX:p.x,clientY:p.y}})()).inside===false"
        )
        assert js(
            "app.plot.position((()=>{const p=new DOMPoint(app.plot.geometry().centerX,app.plot.geometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {clientX:p.x,clientY:p.y}})()).delay_us===0"
        )

    assert js(
        "(()=>{const saved=app.controller.targets,old=app.controller.selected;let ok=true;for(const d of [0,app.controller.state.max_delay_us]){app.controller.targets=[{delay_us:d,doppler_hz:0,gain_db:-18,enabled:false}];app.controller.selected=0;app.renderEditor();ok=ok&&document.getElementById('range').checkValidity();}app.controller.targets=saved;app.controller.selected=old;app.renderEditor();return ok;})()"
    )
    js("document.getElementById('fit').click()")
    assert js("document.querySelectorAll('#targets g').length===4")
    js("app.controller.changed();app.controller.flush()")
    time.sleep(0.8)
    st = request("state")[1]
    assert all(t["enabled"] for t in st["targets"])
    js("app.plot.select(0)")
    assert js(
        "document.getElementById('visible').tagName==='BUTTON' && document.getElementById('visible').getAttribute('aria-pressed')==='true'"
    )
    assert js("!document.querySelector('input[type=checkbox]')")
    js("document.getElementById('visible').click();app.controller.flush()")
    time.sleep(0.3)
    assert not request("state")[1]["targets"][0]["enabled"]
    assert js(
        "document.getElementById('visible').getAttribute('aria-pressed')==='false'"
    )
    js("document.getElementById('visible').click();app.controller.flush()")
    time.sleep(0.3)
    before_gain = request("state")[1]["targets"]
    for channel, value in (("tx", -35.25), ("rx", 30)):
        js(
            f"document.getElementById('{channel}-gain').value={value};document.getElementById('{channel}-gain').dispatchEvent(new Event('change'))"
        )
        time.sleep(0.4)
        actual = request("state")[1]
        assert actual[channel + "_gain_db"] == value
        assert actual["targets"] == before_gain, (
            "Radio gain edits must preserve the scene",
            before_gain,
            actual["targets"],
        )
    import adi

    radio = adi.Pluto("ip:" + urllib.parse.urlparse(base).hostname)
    assert radio.rx_hardwaregain_chan0 == 30 and radio.tx_hardwaregain_chan0 == -35.25
    assert radio.gain_control_mode_chan0 == "manual"
    assert radio.rx_rf_bandwidth == radio.tx_rf_bandwidth == 20000000
    assert (
        abs(
            radio._get_iio_attr("voltage0", "sampling_frequency", False)
            - initial_radio["sample_rate_hz"]
        )
        < 100
    )

    assert all(
        abs(t["delay_us"] - u["delay_us"]) <= st["delay_step_us"] / 2 + 1e-8
        for t, u in zip(st["targets"], scene["targets"])
    )
    # Continuous logarithmic zoom changes only the view and zooms only the hovered control.
    before_zoom = request("state")[1]["targets"]
    assert js(
        "(()=>{app.plot.setWindow('range',123.456);app.plot.setWindow('velocity',2.345);app.plot.draw();return Math.abs(app.plot.windowValue('range')-123.456)<1e-6 && Math.abs(app.plot.windowValue('velocity')-2.345)<1e-6;})()"
    )
    for element, axis in (
        ("plot", None),
        ("range-axis-title", "range"),
        ("velocity-axis-title", "velocity"),
    ):
        result = js(
            "(()=>{const a=app.plot.windowValue('range'),b=app.plot.windowValue('velocity');const e=new WheelEvent('wheel',{deltaY:-100,bubbles:true,cancelable:true});document.getElementById("
            + json.dumps(element)
            + ").dispatchEvent(e);return {range:app.plot.windowValue('range')/a,velocity:app.plot.windowValue('velocity')/b,prevented:e.defaultPrevented};})()"
        )
        assert (result["range"] < 0.99) == (axis == "range"), result
        assert (result["velocity"] < 0.99) == (axis == "velocity"), result
        assert result["prevented"] == (axis is not None)
    js(
        "document.getElementById('range-axis-title').dispatchEvent(new MouseEvent('click',{bubbles:true}))"
    )
    assert js(
        "!document.getElementById('zoom-popover').hidden && document.getElementById('zoom-popover').textContent.includes('mouse wheel')"
    )
    old_range = js("app.plot.rangeMaximum")
    js(
        "document.getElementById('zoom-slider').value=.65;document.getElementById('zoom-slider').dispatchEvent(new Event('input'))"
    )
    assert js("app.plot.rangeMaximum") != old_range
    js("document.getElementById('zoom-close').click()")
    assert js("document.getElementById('zoom-popover').hidden")
    # The gain cue remains distinguishable throughout the common high-gain range.
    radii = js(
        "(()=>{const t=app.controller.targets[0],saved=t.gain_db;const values=[-10,-6,-3,-1].map(g=>{t.gain_db=g;app.plot.draw();return Number(document.querySelector('.gain-aura').getAttribute('r'));});t.gain_db=saved;app.plot.draw();return values;})()"
    )
    assert all(b - a > 2 for a, b in zip(radii, radii[1:])), radii
    assert request("state")[1]["targets"] == before_zoom
    assert js(
        "(()=>{app.plot.setWindow('range',0);app.plot.setWindow('velocity',1e20);app.plot.draw();return app.plot.windowValue('range')>sceneModel.latency(app.controller.state)*sceneModel.METERS_PER_US && Math.abs(app.plot.windowValue('velocity')-1000)<1e-6;})()"
    )
    js("document.getElementById('fit').click()")
    # Range entry is total range; readback remains the FPGA's added delay.
    js(
        "app.plot.select(0);document.getElementById('range').value=(sceneModel.latency(app.controller.state)+1)*sceneModel.METERS_PER_US;document.getElementById('range').dispatchEvent(new Event('change'))"
    )
    time.sleep(0.6)
    assert (
        abs(request("state")[1]["targets"][0]["delay_us"] - 1)
        <= initial_radio["delay_step_us"] / 2 + 1e-8
    )
    assert js(
        "document.getElementById('delay-display').textContent===`${(app.controller.targets[0].delay_us+sceneModel.latency(app.controller.state)).toLocaleString(undefined,{maximumFractionDigits:5})} µs`"
    )
    # A click on the marker's rim must not move it. A drag preserves the grab offset.
    js(
        "app.plot.setWindow('range',350);app.plot.setWindow('velocity',10);app.plot.draw()"
    )
    start = js(
        "(()=>{const p=app.plot.point(app.controller.targets[0]);const q=new DOMPoint(p.x+6,p.y+3).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y};})()"
    )
    before = request("state")[1]["targets"][0]
    call(
        "Input.dispatchMouseEvent",
        dict(type="mousePressed", button="left", buttons=1, clickCount=1, **start),
    )
    call(
        "Input.dispatchMouseEvent",
        dict(
            type="mouseMoved",
            button="left",
            buttons=1,
            x=start["x"] + 1,
            y=start["y"] + 1,
        ),
    )
    call(
        "Input.dispatchMouseEvent",
        dict(
            type="mouseReleased",
            button="left",
            buttons=0,
            clickCount=1,
            x=start["x"] + 1,
            y=start["y"] + 1,
        ),
    )
    assert js("app.controller.targets[0].delay_us") == before["delay_us"]
    call(
        "Input.dispatchMouseEvent",
        dict(type="mousePressed", button="left", buttons=1, clickCount=1, **start),
    )
    end = js(
        "(()=>{const p=app.plot.point(app.controller.targets[0]);const q=new DOMPoint(p.x+66,p.y-37).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y};})()"
    )
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseMoved", button="left", buttons=1, **end),
    )
    time.sleep(0.3)
    assert (
        request("state")[1]["targets"][0] != before
    ), "Drag must update hardware before release"
    assert js(
        "app.plot.drag.moved && Math.abs(app.plot.drag.dx-6)<1e-3 && Math.abs(app.plot.drag.dy-3)<1e-3"
    )
    expected = js("app.controller.targets[0].delay_us")
    expected_doppler = js("app.controller.targets[0].doppler_hz")
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseReleased", button="left", buttons=0, clickCount=1, **end),
    )
    time.sleep(0.6)
    after = request("state")[1]["targets"][0]
    assert abs(after["delay_us"] - expected) < 1e-7
    assert (
        abs(after["doppler_hz"] - expected_doppler) <= st["doppler_step_hz"] / 2 + 1e-8
    )
    assert (
        after["delay_us"] > before["delay_us"]
        and after["doppler_hz"] < before["doppler_hz"]
    )
    # Dragging into the shaded band stops at zero added delay, including live RF readback.
    start = js(
        "(()=>{const p=app.plot.point(app.controller.targets[0]);const q=new DOMPoint(p.x,p.y).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()"
    )
    end = js(
        "(()=>{const q=new DOMPoint(app.plot.geometry().centerX,app.plot.geometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()"
    )
    call(
        "Input.dispatchMouseEvent",
        dict(type="mousePressed", button="left", buttons=1, clickCount=1, **start),
    )
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseMoved", button="left", buttons=1, **end),
    )
    time.sleep(0.3)
    assert request("state")[1]["targets"][0]["delay_us"] == 0
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseReleased", button="left", buttons=0, clickCount=1, **end),
    )
    time.sleep(0.3)
    js(
        "window.blockedTestScene=app.controller.targets;app.controller.targets=app.controller.targets.slice(0,3);app.plot.draw()"
    )
    call(
        "Input.dispatchMouseEvent",
        dict(type="mousePressed", button="left", buttons=1, clickCount=1, **end),
    )
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseReleased", button="left", buttons=0, clickCount=1, **end),
    )
    assert js(
        "app.controller.targets.length===3"
    ), "Click in blocked region added a target"
    # Empty-space clicks never create a target; the legend keeps its height.
    assert js(
        "(()=>{const h=document.getElementById('target-list').getBoundingClientRect().height;app.controller.targets=[];app.plot.draw();return document.getElementById('target-list').getBoundingClientRect().height===h;})()"
    )
    empty_point = js(
        "(()=>{const p=app.plot.geometry();const q=new DOMPoint(p.centerX,p.top+20).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()"
    )
    call(
        "Input.dispatchMouseEvent",
        dict(
            type="mousePressed", button="left", buttons=1, clickCount=1, **empty_point
        ),
    )
    call(
        "Input.dispatchMouseEvent",
        dict(
            type="mouseReleased", button="left", buttons=0, clickCount=1, **empty_point
        ),
    )
    assert js("app.controller.targets.length===0"), "Empty-space click added a target"
    js("app.controller.targets=window.blockedTestScene;app.plot.draw()")

    # Round trip scene JSON in-browser, without writing downloads to the host.
    js(
        "window.savedCreateURL=URL.createObjectURL;window.savedClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{window.exportedBlob=b;return 'blob:preview'};HTMLAnchorElement.prototype.click=()=>{};document.getElementById('export').click();URL.createObjectURL=window.savedCreateURL;HTMLAnchorElement.prototype.click=window.savedClick"
    )
    exported = js("exportedBlob.text().then(JSON.parse)")
    assert exported["version"] == 1 and len(exported["targets"]) == 4
    js(
        "(async()=>{const transfer=new DataTransfer();const scene=JSON.parse(await exportedBlob.text());scene.targets[0].gain_db=-21;transfer.items.add(new File([JSON.stringify(scene)],'scene.json',{type:'application/json'}));document.getElementById('file').files=transfer.files;document.getElementById('file').dispatchEvent(new Event('change'));})()"
    )
    time.sleep(0.6)
    assert js("app.controller.targets.length===4 && !app.controller.dirty")
    assert len(request("state")[1]["targets"]) == 4
    assert abs(request("state")[1]["targets"][0]["gain_db"] + 21) < 0.01
    js("document.getElementById('fit').click()")
    assert js(
        "getComputedStyle(document.querySelector('.axis-title')).fontSize==='19px'"
    )
    assert js(
        "(()=>{const r=[...document.querySelectorAll('.target-summary')].map(e=>e.getBoundingClientRect());return r.every(x=>Math.abs(x.y-r[0].y)<1);})()"
    )
    assert js(
        "!document.getElementById('delay-window') && !document.getElementById('doppler-window')"
    )
    assert js(
        "(()=>{const radio=document.querySelector('.radio-panel').getBoundingClientRect(),plot=document.querySelector('.plot-card').getBoundingClientRect(),editor=document.querySelector('aside').getBoundingClientRect();return radio.right<plot.left && plot.right<editor.left && document.querySelector('.radio-panel').contains(document.getElementById('bandwidth'));})()"
    )
    # Movement is executed on Pluto; toggling it must update the API and animate.
    js(
        "window.beforeMotionScene=app.controller.targets.map(t=>({...t}));app.controller.replace([{enabled:true,delay_us:.5,doppler_hz:-100/sceneModel.velocityPerHz(app.controller.state),gain_db:-24}]);app.controller.flush()"
    )
    js(
        "app.plot.select(0);document.getElementById('movement').click();app.controller.flush()"
    )
    assert request("state")[1]["targets"][0]["realistic_movement"]
    first_delay = request("state")[1]["targets"][0]["delay_us"]
    time.sleep(0.4)
    assert request("state")[1]["targets"][0]["delay_us"] > first_delay
    js("app.controller.refresh()")
    first_marker = js(
        "document.querySelector('#targets .target').getAttribute('transform')"
    )
    time.sleep(0.04)
    assert (
        js("document.querySelector('#targets .target').getAttribute('transform')")
        != first_marker
    )
    js("document.getElementById('movement').click();app.controller.flush()")
    stopped = request("state")[1]["targets"]
    time.sleep(0.15)
    assert request("state")[1]["targets"] == stopped
    assert not stopped[0]["realistic_movement"]
    js("app.controller.replace(window.beforeMotionScene);app.controller.flush()")
    # Fit with all targets and inspector open, including browser chrome / 125% scale equivalents.
    for width, height in ((1920, 1080), (1920, 900), (1536, 760), (1280, 720)):
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=width, height=height, deviceScaleFactor=1, mobile=False),
        )
        time.sleep(0.1)
        assert js(
            "document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth"
        ), (width, height)
        assert js(
            "document.querySelector('.plot-card').getBoundingClientRect().bottom<=innerHeight"
        ), (width, height)
    call(
        "Emulation.setDeviceMetricsOverride",
        dict(width=1920, height=900, deviceScaleFactor=1, mobile=False),
    )
    (root / "build/device-web-desktop.png").write_bytes(
        base64.b64decode(
            call(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": True},
            )["data"]
        )
    )
    call(
        "Emulation.setDeviceMetricsOverride",
        dict(width=390, height=844, deviceScaleFactor=1, mobile=True),
    )
    time.sleep(0.2)
    assert js("document.documentElement.scrollWidth<=innerWidth")
    # Real two-contact touch events must zoom the plot without moving targets.
    js(
        "document.getElementById('plot').scrollIntoView({block:'center'});app.plot.setWindow('range',800);app.plot.setWindow('velocity',10);app.plot.draw()"
    )
    touch_box = js(
        "(()=>{const r=document.getElementById('plot').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()"
    )
    before_pinch = request("state")[1]["targets"]

    def contacts(spread):
        return [
            dict(
                id=i + 1,
                x=touch_box["x"] + touch_box["w"] * (0.6 + direction * spread),
                y=touch_box["y"] + touch_box["h"] * 0.6,
            )
            for i, direction in enumerate((-1, 1))
        ]

    call(
        "Input.dispatchTouchEvent", dict(type="touchStart", touchPoints=contacts(0.10))
    )
    for spread in (0.12, 0.14, 0.16, 0.18):
        call(
            "Input.dispatchTouchEvent",
            dict(type="touchMove", touchPoints=contacts(spread)),
        )
    call("Input.dispatchTouchEvent", dict(type="touchEnd", touchPoints=[]))
    assert js(
        "app.plot.rangeMaximum<600 && app.plot.velocityMaximum<8 && !app.plot.pinch && app.plot.touches.size===0"
    )
    assert request("state")[1]["targets"] == before_pinch
    js("app.plot.fit();window.scrollTo(0,0)")
    (root / "build/device-web-mobile.png").write_bytes(
        base64.b64decode(
            call(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": True},
            )["data"]
        )
    )
    js(
        "document.getElementById('carrier-input').value=2385;document.getElementById('carrier-input').dispatchEvent(new Event('input'));document.getElementById('carrier-input').dispatchEvent(new Event('change'))"
    )
    time.sleep(0.7)
    assert js(
        "document.getElementById('bandwidth').textContent.includes('2375–2395 MHz')"
    )
    assert not any(t["enabled"] for t in request("state")[1]["targets"])
    js("app.plot.select(0);document.getElementById('visible').click()")
    time.sleep(0.3)
    assert request("state")[1]["targets"][0][
        "enabled"
    ], "Auto-apply must remain active after carrier changes"
    js("document.getElementById('mute').click()")
    time.sleep(0.3)
    assert not any(t["enabled"] for t in request("state")[1]["targets"])
    assert not errors, errors
    print(
        "PASS: target visibility toggle control, axis-label wheel zoom, slider popovers, pinch zoom, gain halos, on-device movement and header status, reserved legend, no click-to-add, RX/TX gain validation and driver readback, scene preservation, rotated axes, centered zero velocity, hidden-target selection, total range, offset-preserving drag and continuous auto-apply, FPGA readback, scene round trip, favicon, actual RF bandwidth, desktop 1080p/900p/720p and mobile layouts"
    )
finally:
    js("app.controller.stop()")
    call(
        "Input.dispatchMouseEvent",
        dict(type="mouseReleased", button="left", buttons=0, clickCount=1, x=0, y=0),
    )
    request("mute", b"")
    request("gain", f"rx {initial_radio['rx_gain_db']}".encode())
    request("gain", f"tx {initial_radio['tx_gain_db']}".encode())
    w.close()
