'use strict';
const $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
const METERS_PER_US=149.896229;
const latency=()=>Number.isFinite(state?.hardware_latency_us)?state.hardware_latency_us:0;
const totalRange=t=>(t.delay_us+latency())*METERS_PER_US;
const colors=['#37c964','#58bde8','#eab85c','#c68be8'];
let carrierDirty=false;const gainPending={rx:false,tx:false};
let state=null,targets=[],selected=-1,dirty=false,localRevision=0,sending=false,muting=false,queued=false,timer=null,drag=null;
const fmt=(x,n=2)=>Number(x).toLocaleString(undefined,{maximumFractionDigits:n});
const frequencyText=x=>Number(x).toLocaleString(undefined,{maximumFractionDigits:2,useGrouping:false});
const velocityPerHz=()=>299792458/(2*(state?.frequency_hz||2380e6));
const maximumRange=()=>((state?.max_delay_us||102.35)+latency())*METERS_PER_US;
const windowLimits=axis=>axis==='range'?[Math.max(3,Math.ceil((latency()*METERS_PER_US+3)/10)*10),maximumRange()]:[.05,1000];
function windowValue(axis){const [lo,hi]=windowLimits(axis),id=axis==='range'?'delay-window':'doppler-window';return lo*Math.pow(hi/lo,Number($(id).value));}
function setWindow(axis,value){const [lo,hi]=windowLimits(axis);$(axis==='range'?'delay-window':'doppler-window').value=Math.log(Math.max(lo,Math.min(hi,value))/lo)/Math.log(hi/lo);}
const rangeCeiling=()=>windowValue('range')/METERS_PER_US;
const rangeSpan=()=>Math.max(0,rangeCeiling()-latency());
const dopplerLimit=()=>windowValue('velocity')/velocityPerHz();
function svg(tag,attrs,parent){const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));parent.append(n);return n;}
function text(x,y,value,parent,attrs={}){const n=svg('text',{x,y,...attrs},parent);n.textContent=value;return n;}
function plotGeometry(){const w=$('plot-wrap').clientWidth,h=$('plot-wrap').clientHeight;return {w,h,left:88,right:w-24,top:24,bottom:h-60,width:w-112,height:h-84,centerX:(88+w-24)/2};}
function draw(){
 $('range-window-value').textContent=`0–${fmt(windowValue('range'),1)} m`;$('velocity-window-value').textContent=`±${fmt(windowValue('velocity'),2)} m/s`;
 const p=plotGeometry();if(p.width<=0||p.height<=0)return;
 $('plot').setAttribute('viewBox',`0 0 ${p.w} ${p.h}`);
 for(const [name,value] of Object.entries({x:p.left,y:p.top,width:p.width,height:p.height}))$('plot-background').setAttribute(name,value);
 $('velocity-axis-title').setAttribute('x',p.centerX);$('velocity-axis-title').setAttribute('y',p.h-12);
 $('range-axis-title').setAttribute('transform',`translate(16,${(p.top+p.bottom)/2}) rotate(-90)`);
 $('empty').setAttribute('x',p.centerX);$('empty').setAttribute('y',(p.top+p.bottom)/2);
 const ax=$('axes');ax.replaceChildren();
 for(let i=0;i<=4;i++){const x=p.left+p.width*i/4;svg('line',{x1:x,y1:p.top,x2:x,y2:p.bottom,stroke:i===2?'#718994':'#2f3b45','stroke-dasharray':i===2?'5 5':'none'},ax);text(x,p.h-35,fmt((i/2-1)*dopplerLimit()*velocityPerHz(),2),ax,{'text-anchor':'middle'});}
 for(let i=0;i<=5;i++){const y=p.bottom-p.height*i/5;svg('line',{x1:p.left,y1:y,x2:p.right,y2:y,stroke:'#2f3b45'},ax);text(p.left-12,y+5,fmt(rangeCeiling()*METERS_PER_US*i/5,1),ax,{'text-anchor':'end'});}
 const blocked=$('unavailable-range');blocked.replaceChildren();
 if(latency()>0){const boundary=p.bottom-p.height*latency()/rangeCeiling();svg('rect',{x:p.left,y:boundary,width:p.width,height:p.bottom-boundary,fill:'#202b32',class:'unavailable-zone'},blocked);svg('rect',{x:p.left,y:boundary,width:p.width,height:p.bottom-boundary,fill:'url(#unavailable-hatch)',class:'unavailable-zone'},blocked);svg('line',{x1:p.left,x2:p.right,y1:boundary,y2:boundary,stroke:'#a8b6bd','stroke-dasharray':'4 4'},ax);text(p.right-8,boundary-8,`Minimum ${fmt(latency()*METERS_PER_US,1)} m`,ax,{'text-anchor':'end',class:'minimum-label'});}
 const group=$('targets');group.replaceChildren();
 targets.forEach((t,i)=>{const {x,y}=targetPoint(t);if(!inView(t))return;
  const g=svg('g',{class:'target',transform:`translate(${x},${y})`,'data-index':i,tabindex:0,role:'button','aria-label':`Target ${i+1}, range ${fmt(totalRange(t))} meters, Doppler ${fmt(t.doppler_hz)} Hz`},group);
  if(i===selected)svg('circle',{r:24,fill:colors[i],opacity:.12},g);
  svg('circle',{r:14,fill:t.enabled?colors[i]:'#aab2bf',stroke:'white','stroke-width':3},g);text(0,4,i+1,g,{'text-anchor':'middle'});
  g.addEventListener('pointerdown',e=>{e.stopPropagation();if(e.button!==0)return;const p=plotPoint(e);selected=i;drag={index:i,id:e.pointerId,dx:p.x-x,dy:p.y-y,startX:e.clientX,startY:e.clientY,moved:false};editor();draw();$('plot').setPointerCapture(e.pointerId);$('plot').classList.add('dragging');});
  g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(i);$('range').focus();}});
 });
 $('empty').style.display=targets.length?'none':'';$('count').textContent=`${targets.length} / 4`;$('add').disabled=targets.length>=4;
 const list=$('target-list');list.replaceChildren();
 targets.forEach((t,i)=>{const b=document.createElement('button');b.className='target-summary'+(i===selected?' selected':'');
  const title=document.createElement('strong');title.textContent=`● ${i+1}${t.enabled?'':' · off'}`;title.style.color=colors[i];b.append(title);
  const details=document.createElement('span');details.textContent=`${fmt(totalRange(t),1)} m · ${fmt(-t.doppler_hz*velocityPerHz(),2)} m/s`;b.append(details);if(!inView(t)){const badge=document.createElement('span');badge.className='outside';badge.textContent='Outside view';b.append(badge);}b.setAttribute('aria-pressed',String(i===selected));b.onclick=()=>select(i);list.append(b);
 });
 const sum=targets.filter(t=>t.enabled).reduce((s,t)=>s+10**(t.gain_db/20),0);
 $('headroom').hidden=sum<=1;$('headroom').textContent='Combined gain may cause clipping. Reduce target gains if needed.';
}
function editor(){const t=targets[selected];$('editor').hidden=!t;$('no-selection').hidden=!!t;$('selected-tag').textContent=t?`Target ${selected+1}`:'None';if(!t)return;
 $('range').min=Math.floor(latency()*METERS_PER_US*1000)/1000;$('range').max=Math.ceil(((state?.max_delay_us||102.35)+latency())*METERS_PER_US*1000)/1000;
 $('range').value=Math.max(Number($('range').min),Math.min(Number($('range').max),Number(totalRange(t).toFixed(3))));
 $('delay-display').textContent=`${fmt(t.delay_us+latency(),5)} µs`;
 $('doppler').value=Number(t.doppler_hz.toFixed(3));$('gain').value=t.gain_db;$('gain-label').textContent=`${fmt(t.gain_db,1)} dB`;$('enabled').setAttribute('aria-pressed',String(t.enabled));$('disabled').setAttribute('aria-pressed',String(!t.enabled));$('enabled').setAttribute('aria-label',`Turn target ${selected+1} on`);$('disabled').setAttribute('aria-label',`Turn target ${selected+1} off`);
}
function targetPoint(t){const p=plotGeometry();return {x:p.centerX-p.width/2*t.doppler_hz/dopplerLimit(),y:p.bottom-p.height*(t.delay_us+latency())/rangeCeiling()};}
function inView(t){return t.delay_us>=-1e-8&&t.delay_us<=rangeSpan()+1e-8&&Math.abs(t.doppler_hz)<=dopplerLimit()+1e-8;}
function showRange(delay){setWindow('range',(delay+latency())*METERS_PER_US*1.05);}
function showVelocity(hz){setWindow('velocity',Math.abs(hz)*velocityPerHz()*1.05);}
function select(i){selected=i;const t=targets[i];if(t){if(t.delay_us>rangeSpan())showRange(t.delay_us);if(Math.abs(t.doppler_hz)>dopplerLimit())showVelocity(t.doppler_hz);}editor();draw();}
function changed(){dirty=true;localRevision++;$('change-status').textContent='Updating…';$('feedback').textContent='';$('feedback').classList.remove('error');draw();if(timer===null)timer=setTimeout(()=>{timer=null;apply();},80);}
function add(delay=rangeSpan()*(.2+.18*targets.length),doppler=dopplerLimit()*([.3,-.3,.55,-.55][targets.length]||0)){if(targets.length>=4)return;targets.push({delay_us:delay,doppler_hz:doppler,gain_db:-18,enabled:true});selected=targets.length-1;editor();changed();}
function plotPoint(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform($('plot').getScreenCTM().inverse());}
function position(e,offset={dx:0,dy:0}){const p=plotPoint(e),g=plotGeometry(),x=p.x-offset.dx,y=p.y-offset.dy;return {delay_us:Math.max(0,Math.min(rangeSpan(),(g.bottom-y)/g.height*rangeCeiling()-latency())),doppler_hz:Math.max(-dopplerLimit(),Math.min(dopplerLimit(),(g.centerX-x)/(g.width/2)*dopplerLimit())),inside:p.x>=g.left&&p.x<=g.right&&p.y>=g.top&&p.y<=g.bottom-g.height*latency()/rangeCeiling()};}
$('plot').addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;if(!drag.moved&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<3)return;drag.moved=true;const p=position(e,drag),step=state?.delay_step_us||.05;Object.assign(targets[drag.index],{delay_us:Math.max(0,Math.min(state?.max_delay_us||102.35,Math.round(p.delay_us/step)*step)),doppler_hz:p.doppler_hz});editor();changed();});
function endDrag(e){if(!drag||e.pointerId!==drag.id)return;drag=null;$('plot').classList.remove('dragging');if($('plot').hasPointerCapture(e.pointerId))$('plot').releasePointerCapture(e.pointerId);clearTimeout(timer);timer=null;if(dirty)apply();}
$('plot').addEventListener('pointerup',endDrag);$('plot').addEventListener('pointercancel',endDrag);
$('plot').addEventListener('lostpointercapture',e=>{if(drag)endDrag(e);});
$('add').onclick=()=>add();$('delay-window').oninput=draw;$('doppler-window').oninput=draw;
const wheelAxes={range:true,velocity:true};
for(const axis of ['range','velocity'])$(axis+'-zoom').onclick=e=>{if(e.target.tagName==='INPUT')return;wheelAxes[axis]=!wheelAxes[axis];$(axis+'-wheel').setAttribute('aria-pressed',String(wheelAxes[axis]));$(axis+'-zoom').classList.toggle('selected',wheelAxes[axis]);};
$('plot').addEventListener('wheel',e=>{if((!wheelAxes.range&&!wheelAxes.velocity)||drag)return;e.preventDefault();const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?plotGeometry().h:1),factor=Math.exp(Math.max(-.5,Math.min(.5,delta*.002)));for(const axis of ['range','velocity'])if(wheelAxes[axis])setWindow(axis,windowValue(axis)*factor);draw();},{passive:false});
$('range').addEventListener('change',()=>{if(selected<0)return;const n=Number($('range').value);if(!Number.isFinite(n)||!$('range').checkValidity()){error(Error('Range is outside the available window'));return;}const step=state?.delay_step_us||.05;targets[selected].delay_us=Math.min(state?.max_delay_us||102.35,Math.max(0,Math.round((n/METERS_PER_US-latency())/step)*step));changed();select(selected);});
$('fit').onclick=()=>{
 const maxDelay=Math.max(0,...targets.map(t=>t.delay_us)),speed=Math.max(0,...targets.map(t=>Math.abs(t.doppler_hz)*velocityPerHz()));
 showRange(maxDelay);
 showVelocity(speed/velocityPerHz());draw();
};
for(const [id,key] of [['doppler','doppler_hz'],['gain','gain_db']])$(id).addEventListener(id==='gain'?'input':'change',()=>{if(selected<0)return;const n=Number($(id).value);if(!Number.isFinite(n)||$(id).value==='')return;targets[selected][key]=n;if(id==='gain')$('gain-label').textContent=`${fmt(n,1)} dB`;changed();if(id==='doppler')select(selected);});
for(const [id,enabled] of [['enabled',true],['disabled',false]])$(id).onclick=()=>{if(selected>=0&&targets[selected].enabled!==enabled){targets[selected].enabled=enabled;editor();changed();}};
$('remove').onclick=()=>{targets.splice(selected,1);selected=Math.min(selected,targets.length-1);editor();changed();};
function error(e){$('feedback').textContent=e.message;$('feedback').classList.add('error');$('change-status').textContent='Could not apply';}
async function request(path,data){
 if(window.RADAR_DEVICE){
  path=path.replace('/api/','/cgi-bin/radar.cgi/');
  if(data!==undefined){
   if(path.endsWith('/apply')){
    if(!Array.isArray(data.targets)||data.targets.length>4)throw Error('Expected up to four targets');
    let mask=0;const rows=[];
    data.targets.forEach((t,i)=>{if(![t.delay_us,t.doppler_hz,t.gain_db].every(Number.isFinite)||t.delay_us<0||t.delay_us>(state?.max_delay_us||102.35)||Math.abs(t.doppler_hz)>=(state?.sample_rate_hz||20e6)/2||t.gain_db< -90||t.gain_db>0)throw Error('Target value out of range');if(t.enabled)mask|=1<<i;rows.push(`${Math.round(t.delay_us*(state?.sample_rate_hz||20e6)/1e6)} ${Math.round(t.doppler_hz/(state?.sample_rate_hz||20e6)*2**32)>>>0} ${Math.min(32767,Math.round(32768*10**(t.gain_db/20)))}`);});
    while(rows.length<4)rows.push('0 0 0');data=[mask,...rows].join('\n');
   }else if(path.endsWith('/radio'))data=String(data.frequency_hz);else if(path.endsWith('/gain'))data=`${data.channel} ${data.gain_db}`;else data='';
   const r=await fetch(path,{method:'POST',headers:{'Content-Type':'text/plain'},body:data});const body=await r.json();if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);return body;
  }
 }
 const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(body.error||`HTTP ${r.status}`);return body;}
function connection(s){const previous=state?windowValue('range'):1500;state=s;setWindow('range',previous);
 $('radio-gains').hidden=!window.RADAR_DEVICE;
 for(const ch of ['rx','tx']){const field=$(ch+'-gain');if(!gainPending[ch]&&document.activeElement!==field&&Number.isFinite(s[ch+'_gain_db']))field.value=s[ch+'_gain_db'];}
 for(const ch of ['rx','tx']){if(Number.isFinite(s[ch+'_gain_min_db'])){$(ch+'-gain').min=s[ch+'_gain_min_db'];$(ch+'-gain').max=s[ch+'_gain_max_db'];$(ch+'-gain').step=s[ch+'_gain_step_db'];}}
const known=Number.isFinite(s.hardware_latency_us);$('sample-rate').textContent=`Sample rate ${fmt(s.sample_rate_hz/1e6,2)} MSa/s`;$('sample-rate').title='Digital processing rate, not RF bandwidth';const bw=Math.min(s.rx_bandwidth_hz||20e6,s.tx_bandwidth_hz||20e6);$('bandwidth').textContent=`RF bandwidth ${fmt(bw/1e6)} MHz · ≈ ${frequencyText((s.frequency_hz-bw/2)/1e6)}–${frequencyText((s.frequency_hz+bw/2)/1e6)} MHz`;$('bandwidth').title='Nominal analog passband; filter edges roll off gradually';$('delay-caption').textContent=known?'Total delay':'Added delay';$('range-axis-title').textContent=known?'Total range (m)':'Range offset (m)';
$('carrier-form').hidden=!window.RADAR_DEVICE;if(!carrierDirty&&document.activeElement!==$('carrier-input'))$('carrier-input').value=Number((s.frequency_hz/1e6).toFixed(6));$('connection').textContent=s.mode==='demo'?'Demo · no RF output':s.connected?'Pluto connected':'Pluto unavailable';$('connection').className='status '+(s.mode==='demo'?'demo':s.connected?'online':'');}
async function apply(){if(muting)return;if(sending){queued=true;return;}sending=true;const rev=localRevision;$('change-status').textContent='Applying scene…';try{const s=await request('/api/apply',{targets});connection(s);if(rev===localRevision&&!drag&&!muting){targets=s.targets;dirty=false;editor();draw();$('change-status').textContent=s.mode==='demo'?'Preview updated':'Scene applied';$('feedback').textContent=s.clipped?'Clipping detected. Reduce gain.':'';$('feedback').classList.toggle('error',s.clipped);}}catch(e){error(e);}finally{sending=false;if(queued){queued=false;apply();}}}
$('mute').onclick=async()=>{let syncScene=false;muting=true;clearTimeout(timer);timer=null;queued=false;try{while(sending)await new Promise(r=>setTimeout(r,20));const s=await request('/api/mute',{});connection(s);targets.forEach(t=>t.enabled=false);syncScene=true;localRevision++;dirty=true;editor();draw();$('change-status').textContent='All echoes muted';$('feedback').textContent='';}catch(e){error(e);}finally{muting=false;if(syncScene&&dirty)apply();}};
for(const channel of ['rx','tx'])$(channel+'-gain').onchange=async()=>{
 const field=$(channel+'-gain');if(field.value===''||!field.checkValidity())return;
 const value=Number(field.value);if(!Number.isFinite(value)||gainPending[channel])return;
 gainPending[channel]=true;field.disabled=true;
 try{const s=await request('/api/gain',{channel,gain_db:value});connection(s);field.value=s[channel+'_gain_db'];$('feedback').textContent='';$('feedback').classList.remove('error');}
 catch(e){error(e);}finally{gainPending[channel]=false;field.disabled=false;}
};
$('carrier-input').oninput=()=>{carrierDirty=true;};
$('carrier-input').onchange=()=>{if(carrierDirty)$('carrier-form').requestSubmit();};
$('carrier-form').onsubmit=async e=>{e.preventDefault();if(muting)return;let syncScene=false;muting=true;clearTimeout(timer);timer=null;queued=false;$('carrier-input').disabled=true;
 try{while(sending)await new Promise(r=>setTimeout(r,20));const hz=Math.round(Number($('carrier-input').value)*1e6);if(!Number.isFinite(hz)||hz<325e6||hz>3800e6)throw Error('Carrier must be between 325 and 3800 MHz');const s=await request('/api/radio',{frequency_hz:hz});carrierDirty=false;connection(s);$('carrier-input').value=s.frequency_hz/1e6;targets.forEach(t=>t.enabled=false);syncScene=true;localRevision++;dirty=true;editor();draw();$('change-status').textContent='Carrier set · targets muted';$('feedback').textContent='';$('feedback').classList.remove('error');
 }catch(e){error(e);}finally{muting=false;$('carrier-input').disabled=false;if(syncScene&&dirty)apply();}};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,targets},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='target-scene.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('import').onclick=()=>$('file').click();$('file').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>16384)throw Error('Scene file is too large');const revision=localRevision;const data=JSON.parse(await f.text());if(revision!==localRevision||muting)return;if(!Array.isArray(data.targets)||data.targets.length>4)throw Error('Expected a scene with up to four targets');for(const t of data.targets){if(!['delay_us','doppler_hz','gain_db'].every(k=>typeof t[k]==='number'&&Number.isFinite(t[k]))||typeof t.enabled!=='boolean'||t.delay_us<0||t.delay_us>(state?.max_delay_us||102.35)||Math.abs(t.doppler_hz)>=(state?.sample_rate_hz||20e6)/2||t.gain_db>0||t.gain_db< -90)throw Error('Scene contains an invalid target');}targets=data.targets;selected=targets.length?0:-1;changed();select(selected);}catch(e){error(e);}finally{$('file').value='';}};
async function poll(){const rev=localRevision;try{const s=await request('/api/state');connection(s);if(rev===localRevision&&!dirty&&!sending&&!drag&&!muting){targets=s.targets;selected=Math.min(selected,targets.length-1);if(!$('editor').contains(document.activeElement))editor();draw();}if(s.error){$('feedback').textContent=s.error;$('feedback').classList.add('error');}else if(s.clipped){$('feedback').textContent='Clipping detected. Reduce gain.';$('feedback').classList.add('error');}}catch(e){$('connection').textContent='Controller unavailable';$('connection').className='status';}finally{setTimeout(poll,2500);}}
setWindow('range',1500);setWindow('velocity',10);
new ResizeObserver(draw).observe($('plot-wrap'));draw();poll();
