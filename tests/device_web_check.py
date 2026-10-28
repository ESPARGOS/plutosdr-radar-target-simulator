"""Live Pluto CGI and browser check; leaves targets muted."""
import base64,json,os,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
import websocket
root=Path(__file__).resolve().parents[1];base=os.environ.get('PLUTO_URL','http://192.168.4.1').rstrip('/')
def request(path,data=None,origin=None):
 headers={'Content-Type':'text/plain'}
 if origin:headers['Origin']=origin
 try:
  r=urllib.request.urlopen(urllib.request.Request(base+'/cgi-bin/radar.cgi/'+path,data=data,headers=headers),timeout=6)
  return r.status,json.load(r)
 except urllib.error.HTTPError as e:return e.code,json.load(e)
assert request('apply',b'15\n-1 0 1')[0]==400
assert request('apply',b'15\n'+b'2048 0 1\n'*4)[0]==400
assert request('mute',b'',origin='http://example.invalid')[0]==403
assert request('radio',b'100000000')[0]==400
assert request('radio',b'2380000000garbage')[0]==400
initial_radio=request('state')[1]
assert initial_radio['connected']
for payload in (b'rx nan',b'tx inf',b'rx 30.5',b'tx -0.2',b'rx 9999',b'tx -100',b'tx -30 extra',b'bad 5'):
 assert request('gain',payload)[0]==400,payload
assert request('gain',b'tx -35',origin='http://example.invalid')[0]==403
debug_origin='http://localhost:'+os.environ.get('RADAR_BROWSER_DEBUG_PORT','9223')
tabs=json.load(urllib.request.urlopen(debug_origin+'/json'))
tab=next(t for t in tabs if t.get('type')=='page' and not t['url'].startswith('chrome://'))
w=websocket.create_connection(tab['webSocketDebuggerUrl'],origin=debug_origin);seq=0;errors=[]
def call(method,params=None):
 global seq
 seq+=1;w.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
 while True:
  r=json.loads(w.recv())
  if r.get('method')=='Runtime.exceptionThrown':errors.append(r)
  if r.get('id')==seq:
   if 'error' in r:raise RuntimeError(r['error'])
   return r.get('result',{})
def js(expression):
 r=call('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
 if 'exceptionDetails' in r:raise RuntimeError(r)
 return r['result'].get('value')
try:
 call('Runtime.enable');call('Page.enable');call('Network.enable');call('Network.setCacheDisabled',{'cacheDisabled':True})
 call('Emulation.setDeviceMetricsOverride',dict(width=1920,height=900,deviceScaleFactor=1,mobile=False));call('Page.navigate',{'url':base+'/'})
 for _ in range(60):
  if js('window.RADAR_DEVICE && typeof state!=="undefined" && state?.connected'):break
  time.sleep(.25)
 assert js('window.RADAR_DEVICE && state.hardware_latency_us===.325')
 assert js("document.getElementById('fit').form===null && document.getElementById('rx-gain').form===null")
 assert js("!document.getElementById('live') && !document.getElementById('apply')")
 assert js("document.getElementById('sample-rate').textContent==='Sample rate 160 MSa/s'")
 assert js("document.getElementById('bandwidth').textContent.includes('RF bandwidth 20 MHz')")
 assert js("document.getElementById('range-axis-title').textContent==='Total range (m)'")
 assert js("[...document.querySelectorAll('.axis-title')].some(x=>x.textContent==='Radial velocity (m/s)')")
 assert js("document.querySelector('link[rel=icon]').href.endsWith('/favicon.ico')")
 assert urllib.request.urlopen(base+'/favicon.ico').read()==(root/'web/favicon.ico').read_bytes()
 assert js("document.querySelector('.brand img').naturalWidth")>0
 scene=json.loads((root/'config/four-targets.json').read_text())
 js('targets='+json.dumps(scene['targets'])+'; selected=0; dirty=true; editor(); draw();')
 # Small windows may hide targets, but never move velocity zero away from center.
 js("setWindow('range',65);setWindow('velocity',.25);draw()")
 assert js("targetPoint({delay_us:0,doppler_hz:0}).x===plotGeometry().centerX")
 assert js("document.querySelectorAll('.outside').length>0")
 js("document.querySelectorAll('.target-summary')[3].click()")
 assert js("inView(targets[3]) && targetPoint({delay_us:0,doppler_hz:0}).x===plotGeometry().centerX")
 assert js("Math.abs(totalRange({delay_us:0})-48.716274425)<1e-8")
 assert js("document.querySelectorAll('#unavailable-range rect').length===2 && !document.getElementById('range-note')")
 assert js("position((()=>{const p=new DOMPoint(plotGeometry().centerX,plotGeometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {clientX:p.x,clientY:p.y}})()).inside===false")
 assert js("position((()=>{const p=new DOMPoint(plotGeometry().centerX,plotGeometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {clientX:p.x,clientY:p.y}})()).delay_us===0")

 assert js("(()=>{const saved=targets,old=selected;let ok=true;for(const d of [0,state.max_delay_us]){targets=[{delay_us:d,doppler_hz:0,gain_db:-18,enabled:false}];selected=0;editor();ok=ok&&document.getElementById('range').checkValidity();}targets=saved;selected=old;editor();return ok;})()")
 js("document.getElementById('fit').click()")
 assert js("document.querySelectorAll('#targets g').length===4")
 js("changed()");time.sleep(.8)
 st=request('state')[1]
 assert all(t['enabled'] for t in st['targets'])
 js('select(0)')
 assert js("document.getElementById('enabled').tagName==='BUTTON' && document.getElementById('enabled').getAttribute('aria-pressed')==='true'")
 assert js("!document.querySelector('input[type=checkbox]')")
 js("document.getElementById('disabled').click()");time.sleep(.3)
 assert not request('state')[1]['targets'][0]['enabled']
 assert js("document.getElementById('disabled').getAttribute('aria-pressed')==='true' && document.getElementById('enabled').getAttribute('aria-pressed')==='false'")
 js("document.getElementById('enabled').click()");time.sleep(.3)
 before_gain=request('state')[1]['targets']
 for channel,value in (('tx',-35.25),('rx',30)):
  js(f"document.getElementById('{channel}-gain').value={value};document.getElementById('{channel}-gain').dispatchEvent(new Event('change'))")
  time.sleep(.4)
  actual=request('state')[1]
  assert actual[channel+'_gain_db']==value
  assert actual['targets']==before_gain,'Radio gain edits must preserve the scene'
 import adi
 radio=adi.Pluto('ip:'+urllib.parse.urlparse(base).hostname)
 assert radio.rx_hardwaregain_chan0==30 and radio.tx_hardwaregain_chan0==-35.25
 assert radio.gain_control_mode_chan0=='manual'
 assert radio.rx_rf_bandwidth==radio.tx_rf_bandwidth==20000000
 assert abs(radio._get_iio_attr('voltage0','sampling_frequency',False)-160e6)<100

 assert all(abs(t['delay_us']-u['delay_us'])<=st['delay_step_us']/2+1e-8 for t,u in zip(st['targets'],scene['targets']))
 # Continuous logarithmic zoom changes only the view and respects wheel selection.
 before_zoom=request('state')[1]['targets']
 assert js("(()=>{setWindow('range',123.456);setWindow('velocity',2.345);draw();return Math.abs(windowValue('range')-123.456)<1e-6 && Math.abs(windowValue('velocity')-2.345)<1e-6;})()")
 for mode in ('range','velocity','both','off'):
  result=js("(()=>{window.testWheelMode="+json.dumps(mode)+";for(const axis of ['range','velocity']){const wanted=testWheelMode==='both'||testWheelMode===axis;if(wheelAxes[axis]!==wanted)document.getElementById(axis+'-wheel').click();}const a=windowValue('range'),b=windowValue('velocity');const e=new WheelEvent('wheel',{deltaY:-100,bubbles:true,cancelable:true});document.getElementById('plot').dispatchEvent(e);return {range:windowValue('range')/a,velocity:windowValue('velocity')/b,prevented:e.defaultPrevented};})()")
  assert (result['range']<.99)==(mode in ('range','both')),result
  assert (result['velocity']<.99)==(mode in ('velocity','both')),result
  assert result['prevented']==(mode!='off')
 assert request('state')[1]['targets']==before_zoom
 assert js("(()=>{setWindow('range',0);setWindow('velocity',1e20);draw();return windowValue('range')>latency()*METERS_PER_US && Math.abs(windowValue('velocity')-1000)<1e-6;})()")
 js("for(const axis of ['range','velocity'])if(!wheelAxes[axis])document.getElementById(axis+'-wheel').click();document.getElementById('fit').click()")
 # Range entry is total range; readback remains the FPGA's added delay.
 js("select(0);document.getElementById('range').value=(latency()+1)*METERS_PER_US;document.getElementById('range').dispatchEvent(new Event('change'))")
 time.sleep(.6);assert abs(request('state')[1]['targets'][0]['delay_us']-1)<1e-7
 assert js("document.getElementById('delay-display').textContent.includes('1.325')")
 # A click on the marker's rim must not move it. A drag preserves the grab offset.
 js("setWindow('range',350);setWindow('velocity',10);draw()")
 start=js("(()=>{const p=targetPoint(targets[0]);const q=new DOMPoint(p.x+6,p.y+3).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y};})()")
 before=request('state')[1]['targets'][0]
 call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',buttons=1,clickCount=1,**start))
 call('Input.dispatchMouseEvent',dict(type='mouseMoved',button='left',buttons=1,x=start['x']+1,y=start['y']+1))
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,x=start['x']+1,y=start['y']+1))
 assert js('targets[0].delay_us')==before['delay_us']
 call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',buttons=1,clickCount=1,**start))
 end=js("(()=>{const p=targetPoint(targets[0]);const q=new DOMPoint(p.x+66,p.y-37).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y};})()")
 call('Input.dispatchMouseEvent',dict(type='mouseMoved',button='left',buttons=1,**end));time.sleep(.3)
 assert request('state')[1]['targets'][0]!=before,'Drag must update hardware before release'
 assert js('drag.moved && Math.abs(drag.dx-6)<1e-3 && Math.abs(drag.dy-3)<1e-3')
 expected=js('targets[0].delay_us');expected_doppler=js('targets[0].doppler_hz')
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,**end));time.sleep(.6)
 after=request('state')[1]['targets'][0]
 assert abs(after['delay_us']-expected)<1e-7
 assert abs(after['doppler_hz']-expected_doppler)<=st['doppler_step_hz']/2+1e-8
 assert after['delay_us']>before['delay_us'] and after['doppler_hz']<before['doppler_hz']
 # Dragging into the shaded band stops at zero added delay, including live RF readback.
 start=js("(()=>{const p=targetPoint(targets[0]);const q=new DOMPoint(p.x,p.y).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()")
 end=js("(()=>{const q=new DOMPoint(plotGeometry().centerX,plotGeometry().bottom-1).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()")
 call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',buttons=1,clickCount=1,**start))
 call('Input.dispatchMouseEvent',dict(type='mouseMoved',button='left',buttons=1,**end));time.sleep(.3)
 assert request('state')[1]['targets'][0]['delay_us']==0
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,**end));time.sleep(.3)
 js('window.blockedTestScene=targets;targets=targets.slice(0,3);draw()')
 call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',buttons=1,clickCount=1,**end))
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,**end))
 assert js('targets.length===3'),'Click in blocked region added a target'
 # Empty-space clicks never create a target; the legend keeps its height.
 assert js("(()=>{const h=document.getElementById('target-list').getBoundingClientRect().height;targets=[];draw();return document.getElementById('target-list').getBoundingClientRect().height===h;})()")
 empty_point=js("(()=>{const p=plotGeometry();const q=new DOMPoint(p.centerX,p.top+20).matrixTransform(document.getElementById('plot').getScreenCTM());return {x:q.x,y:q.y}})()")
 call('Input.dispatchMouseEvent',dict(type='mousePressed',button='left',buttons=1,clickCount=1,**empty_point))
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,**empty_point))
 assert js('targets.length===0'),'Empty-space click added a target'
 js('targets=window.blockedTestScene;draw()')

 # Round trip scene JSON in-browser, without writing downloads to the host.
 js("window.savedCreateURL=URL.createObjectURL;window.savedClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=b=>{window.exportedBlob=b;return 'blob:preview'};HTMLAnchorElement.prototype.click=()=>{};document.getElementById('export').click();URL.createObjectURL=window.savedCreateURL;HTMLAnchorElement.prototype.click=window.savedClick")
 exported=js('exportedBlob.text().then(JSON.parse)');assert exported['version']==1 and len(exported['targets'])==4
 js("(async()=>{const transfer=new DataTransfer();const scene=JSON.parse(await exportedBlob.text());scene.targets[0].gain_db=-21;transfer.items.add(new File([JSON.stringify(scene)],'scene.json',{type:'application/json'}));document.getElementById('file').files=transfer.files;document.getElementById('file').dispatchEvent(new Event('change'));})()")
 time.sleep(.6);assert js('targets.length===4 && !dirty');assert len(request('state')[1]['targets'])==4;assert abs(request('state')[1]['targets'][0]['gain_db']+21)<.01
 js("document.getElementById('fit').click()")
 assert js("getComputedStyle(document.querySelector('.axis-title')).fontSize==='19px'")
 assert js("(()=>{const r=[...document.querySelectorAll('.target-summary')].map(e=>e.getBoundingClientRect());return r.every(x=>Math.abs(x.y-r[0].y)<1);})()")
 # Fit with all targets and inspector open, including browser chrome / 125% scale equivalents.
 for width,height in ((1920,1080),(1920,900),(1536,760),(1280,720)):
  call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=False));time.sleep(.1)
  assert js('document.documentElement.scrollHeight<=innerHeight && document.documentElement.scrollWidth<=innerWidth'),(width,height)
  assert js("document.querySelector('.action-bar').getBoundingClientRect().bottom<=innerHeight-8"),(width,height)
 call('Emulation.setDeviceMetricsOverride',dict(width=1920,height=900,deviceScaleFactor=1,mobile=False))
 (root/'build/device-web-desktop.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})['data']))
 call('Emulation.setDeviceMetricsOverride',dict(width=390,height=844,deviceScaleFactor=1,mobile=True));time.sleep(.2)
 assert js('document.documentElement.scrollWidth<=innerWidth')
 (root/'build/device-web-mobile.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})['data']))
 js("document.getElementById('carrier-input').value=2385;document.getElementById('carrier-input').dispatchEvent(new Event('input'));document.getElementById('carrier-input').dispatchEvent(new Event('change'))")
 time.sleep(.7)
 assert js("document.getElementById('bandwidth').textContent.includes('2375–2395 MHz')")
 assert not any(t['enabled'] for t in request('state')[1]['targets'])
 js("select(0);document.getElementById('enabled').click()");time.sleep(.3)
 assert request('state')[1]['targets'][0]['enabled'],'Auto-apply must remain active after carrier changes'
 js("document.getElementById('mute').click()");time.sleep(.3)
 assert not any(t['enabled'] for t in request('state')[1]['targets'])
 assert not errors,errors
 print('PASS: joined On/Off control, selectable continuous wheel zoom, reserved legend, no click-to-add, RX/TX gain validation and driver readback, scene preservation, rotated axes, centered zero velocity, hidden-target selection, total range, offset-preserving drag and continuous auto-apply, FPGA readback, scene round trip, favicon, actual RF bandwidth, desktop 1080p/900p/720p and mobile layouts')
finally:
 js("muting=true;clearTimeout(timer);timer=null")
 call('Input.dispatchMouseEvent',dict(type='mouseReleased',button='left',buttons=0,clickCount=1,x=0,y=0))
 request('mute',b'')
 request('gain',f"rx {initial_radio['rx_gain_db']}".encode());request('gain',f"tx {initial_radio['tx_gain_db']}".encode());w.close()
