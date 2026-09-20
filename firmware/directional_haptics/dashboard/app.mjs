import {simulatedFrame} from './simulation.mjs';
const isDemo=new URL(location.href).searchParams.get('demo')==='1';
const $=id=>document.getElementById(id);
const names=['Back · SparkFun envelope','Left · SparkFun envelope','Right · SparkFun envelope'];
const colors=['#1662c4','#b75520','#6546a3'];
let history=[],state=null,lastSeen=0,lastStateAt=0,connected=false,busy=false,actionError='',settingsLoaded=false,mappingLoaded=false;
for(let i=0;i<3;i++){
  const section=document.createElement('section');section.className='sensor';section.style.setProperty('--sensor-color',colors[i]);
  section.dataset.channel=String(i);
  section.innerHTML=`<div class="sensor-title"><h2>A${i} · ${names[i]}</h2><span class="small">Envelope mean is the primary sound measure</span></div>
    <div class="metrics"><div><span>Raw A${i}</span><b id="raw${i}">—</b><small id="volts${i}">ADC counts / 1023</small></div><div><span>Peak-to-peak · 40 ms</span><b id="p2p${i}">—</b><small>ADC counts</small></div><div><span>Envelope · latest window</span><b id="amplitude${i}">—</b><small>ADC counts</small></div><div><span>Peak envelope · 5 s</span><b id="peak${i}">—</b><small>ADC counts</small></div></div>
    <div class="plots"><section class="chart"><h3>Raw signal range</h3><p class="small">Detail view zooms independently. Use the comparison above for equal axes.</p><div class="legend"><span style="color:${colors[i]}">● Mean + observed range</span></div><canvas id="rawPlot${i}" role="img" aria-label="A${i} mean and minimum-to-maximum range"></canvas><p id="range${i}" class="small">Waiting for readings</p></section><section class="chart"><h3>Calibrated response</h3><p class="small">ADC range above the saved floor vs. shaped, smoothed directional output. Both curves use 0–100%.</p><div class="legend"><span class="orange">● ADC range above floor</span><span class="purple">● Smoothed</span></div><canvas id="variationPlot${i}" role="img" aria-label="A${i} calibrated and smoothed response"></canvas><p id="response${i}" class="small">Waiting for readings</p></section></div><p id="quiet${i}" class="quiet-note">Quiet baseline not measured.</p>`;
  $('sensors').append(section);
  const apart=document.createElement('section');apart.className='apart-channel';
  apart.innerHTML=`<h3 style="color:${colors[i]}">A${i} · ${names[i]}</h3><canvas id="apartPlot${i}" role="img" aria-label="A${i} ${names[i]} on the same scale as the other two graphs"></canvas>`;
  $('apartPlots').append(apart);
}
const selectedParameter=new URL(location.href).searchParams.get('sensor');
if(['0','1','2'].includes(selectedParameter))$('viewSensor').value=selectedParameter;
function setView(){
 const selected=$('viewSensor').value,all=selected==='all'||selected==='apart',index=Number(selected);
 for(const element of document.querySelectorAll('#sensors > .sensor, #compareLegend > span'))element.hidden=!all&&element.dataset.channel!==selected;
 $('compareTitle').textContent=selected==='apart'?'Apart · three graphs, same scale':all?'All together · one timeline':`A${index} · ${names[index]}`;
 $('comparePlot').hidden=selected==='apart';$('apartPlots').hidden=selected!=='apart';
 $('comparePlot').setAttribute('aria-label',all?'A0, A1 and A2 on one shared time and amplitude axis':`Individual A${index} signal for inspecting hardware gain`);
 $('gainHint').textContent=all?'A1 = left · A2 = right · A0 = back. Together and Apart use the same amplitude scale and timeline. All three remain sampled and recorded.':`Showing A${index} · ${names[index]} individually. All three inputs remain sampled and recorded. Chart scale changes the display only.`;
 if(isDemo)$('gainHint').textContent='SIMULATED movement. These traces do not read sensors, record data, or send motor commands.';
 render();
}
$('viewSensor').onchange=setView;
$('chartScale').onchange=()=>{$('chartMaximum').disabled=$('chartScale').value!=='fixed';render();};
$('chartMaximum').oninput=()=>{if($('chartMaximum').checkValidity())render();};
setView();
for(const i of [1,2,0]){const card=document.createElement('div');card.innerHTML=`<b style="color:${colors[i]}">${names[i].split(' · ')[0]}</b><span id="motorText${i}">Waiting</span><label>Requested <progress id="targetBar${i}" max="100" value="0"></progress></label><label>Issued effect <progress id="sentBar${i}" max="100" value="0"></progress></label>`;$('motorBars').append(card);}
function timeLabel(seconds){const minutes=Math.floor(seconds/60);return `${String(minutes).padStart(2,'0')}:${(seconds%60).toFixed(1).padStart(4,'0')}`;}
function updateState(next){
  if(state&&state.name!==next.name)history=[];
  state=next;lastStateAt=performance.now();
  $('take').textContent=state.name||'No take';
  $('recordingState').textContent=state.active?'● Recording to this computer':'Recording stopped · live view continues';
  $('saved').textContent=`${state.rows.toLocaleString()} windows saved · ${state.invalid_rows} discarded serial bytes · ${state.missing_windows} missing windows`;
  $('stop').disabled=!connected||busy||!state.active;
  $('newTake').disabled=!connected||busy;
  $('quiet').disabled=!connected||busy||!state.active||!state.live||state.quiet_progress!==null;
  $('reconnect').disabled=!connected||busy;
  $('mark').disabled=!connected||busy||!state.active;
  const lines=state.events.filter(e=>e.type!=='start').slice(-6).map(e=>`${timeLabel(e.elapsed_s)} · ${e.label}`);
  $('events').replaceChildren(...lines.map(text=>{const div=document.createElement('div');div.textContent=text;return div;}));
  const fw=state.firmware;
  if(state?.settings&&!mappingLoaded&&!isDemo){$('sensitivity').value=state.settings.sensitivity;$('contrast').value=state.settings.contrast;$('threshold').value=state.settings.threshold;mappingLoaded=true;}
  if(fw&&!settingsLoaded&&!isDemo){$('profile').value=String(fw.profile);$('ceiling').value=fw.ceiling;for(let i=0;i<3;i++)$('trim'+i).value=fw.trims[i];settingsLoaded=true;}
  const blocked=isDemo||!connected||!state.live||busy||!!state.pending;
  for(const button of document.querySelectorAll('[data-command], [data-trim], #setCeiling, #setProfile, #setSensitivity, #setContrast'))button.disabled=blocked;
  $('qualify').disabled=blocked||!$('observed').checked||fw?.test_mask!==15;
  $('quiet').disabled=blocked||!!fw?.phase||!!fw?.saving;
  $('firmwareState').textContent=isDemo?'SIMULATED DATA · controls disabled · no motor commands':!fw?'Waiting for Rev 3 firmware':`${fw.calibrated?'Calibration loaded':'Calibration required'} · ${fw.qualified?'TITAN setup tested':'TITAN setup not yet tested'} · ${fw.muted?'Muted':'Resumed'} · VH ${fw.profile===20?'2.0':fw.profile===21?'2.1':'unknown'} · ceiling ${fw.ceiling}%${fw.saving?' · saving EEPROM':''}`;
  $('baselineResult').textContent=fw?.phase?`${fw.phase===1?'Quiet calibration':'Microphone matching'}: ${fw.progress}%`:fw?.calibrated?'Noise floors saved. Microphone matching is optional.':'Calibration required: start with five seconds of quiet.';
  $('firmwareAck').textContent=state.pending?`Waiting for Arduino: ${state.pending.name}`:state.last_ack?`${state.last_ack.result}: ${state.last_ack.message}`:'';
  for(let i=0;i<3;i++){const c=fw?.channels[i];$('quiet'+i).textContent=c&&fw.calibrated?`Gate opens at ${c.floor.toFixed(2)}, closes at ${c.close.toFixed(2)} · full output at ${c.reference.toFixed(0)} ADC counts.`:'No valid calibration stored yet.';}
  $('errors').textContent=actionError||state.error||'';
}
function accept(frame){
  if(history.length&&frame.elapsed_s<=history.at(-1).elapsed_s)return;
  history.push(frame);while(history.length>750||history.at(-1).elapsed_s-history[0].elapsed_s>30)history.shift();
  lastSeen=performance.now();
}
if(!isDemo){
const source=new EventSource('/api/events');
source.onopen=()=>{connected=true;};
source.onerror=()=>{connected=false;for(const b of document.querySelectorAll('[data-command],[data-trim]'))b.disabled=true;$('status').textContent='Recorder connection lost · reconnecting';for(const id of ['quiet','mark','newTake','stop','reconnect','qualify','setCeiling','setProfile','setSensitivity','setContrast'])$(id).disabled=true;};
source.onmessage=event=>{
  const message=JSON.parse(event.data);connected=true;
  if(message.type==='snapshot'){history=message.frames;lastSeen=history.length?performance.now():0;}
  if(message.type==='reset')history=[];
  if(message.state)updateState(message.state);
  if(message.frame)accept(message.frame);
};
}
if(isDemo){$('captureHelp').textContent='Display simulation only. No measurements are recorded and no commands are sent.';let seq=0;const at=performance.now();connected=true;setInterval(()=>{const t=(performance.now()-at)/1000,frame=simulatedFrame(t,++seq);accept(frame);updateState({name:'SIMULATED · no recording',active:false,rows:0,elapsed_s:t,live:true,status:'SIMULATED DATA',invalid_rows:0,missing_windows:0,baseline:null,quiet_progress:null,events:[],firmware:frame,pending:null,last_ack:null,error:null});for(const id of ['newTake','stop','quiet','reconnect','mark'])$(id).disabled=true;},40);const download=document.querySelector('a[download]');download.removeAttribute('href');download.textContent='Simulation · no CSV recording';}
async function command(name,data={}){
  if(isDemo)return;
  busy=true;actionError='';if(state)updateState(state);
  try{const response=await fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(result.error||response.statusText);updateState(result);}
  catch(error){actionError=error.message;$('errors').textContent=actionError;}
  finally{busy=false;if(state)updateState(state);}
}
$('newTake').onclick=()=>command('start');$('stop').onclick=()=>command('stop');$('quiet').onclick=()=>command('quiet');
$('reconnect').onclick=()=>command('reconnect');
function firmwareCommand(name,value=0){return command('command',{name,value});}
for(const button of document.querySelectorAll('[data-command]'))button.onclick=()=>firmwareCommand(button.dataset.command,Number(button.dataset.value||0));
$('setSensitivity').onclick=()=>firmwareCommand('SENSITIVITY',Number($('sensitivity').value));
$('setThreshold').onclick=()=>{if($('threshold').reportValidity())firmwareCommand('THRESHOLD',Number($('threshold').value));};
$('setContrast').onclick=()=>firmwareCommand('CONTRAST',Number($('contrast').value));
$('setCeiling').onclick=()=>{if($('ceiling').reportValidity())firmwareCommand('CEILING',Number($('ceiling').value));};
$('setProfile').onclick=()=>{$('observed').checked=false;firmwareCommand('PROFILE',Number($('profile').value));};
$('qualify').onclick=()=>{if($('observed').checked)firmwareCommand('QUALIFY',1);};
$('observed').onchange=()=>{if(state)updateState(state);};
for(const button of document.querySelectorAll('[data-trim]'))button.onclick=()=>{const i=button.dataset.trim;if($('trim'+i).reportValidity())firmwareCommand('TRIM'+i,Number($('trim'+i).value));};
function mark(){const label=$('eventLabel').value.trim()||`Event ${(state?.events.filter(e=>e.type==='marker').length||0)+1}`;command('mark',{label});$('eventLabel').value='';}
$('mark').onclick=mark;$('eventLabel').onkeydown=e=>{if(e.key==='Enter'&&!$('mark').disabled)mark();};
function plot(canvas,series,{band=null,fixedZero=false,bounds=null,displayRange=null}={}){
  const {width:w,height:h}=canvas.getBoundingClientRect();if(!w||!h)return;
  const dpr=Math.min(2,devicePixelRatio||1);if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  let low=0,high=5;
  if(history.length){const values=history.flatMap(t=>series.map(s=>s.value(t)));if(band)for(const t of history)values.push(t.channels[band.index].min,t.channels[band.index].max);low=Math.min(...values);high=Math.max(...values);const pad=Math.max(fixedZero?1:3,(high-low)*.12);low=fixedZero?0:Math.max(bounds?.[0]??-Infinity,low-pad);high=Math.min(bounds?.[1]??Infinity,high+pad);if(high<=low)high=low+1;}
  if(displayRange)[low,high]=displayRange;
  const left=47,right=w-12,top=10,bottom=h-27,y=v=>bottom-(v-low)/(high-low)*(bottom-top),last=history.at(-1)?.elapsed_s||0,x=t=>right-(last-t.elapsed_s)/30*(right-left);
  c.font='11px sans-serif';c.lineWidth=1;
  for(let i=0;i<5;i++){const value=low+(high-low)*i/4,yy=y(value);c.strokeStyle='#e0e8ee';c.beginPath();c.moveTo(left,yy);c.lineTo(right,yy);c.stroke();c.fillStyle='#526d7c';c.fillText(value.toFixed(high-low<20?1:0),2,yy+3);}
  c.fillText('−30 s',left,h-6);c.fillText('now',right-24,h-6);if(!history.length)return;
  c.save();c.beginPath();c.rect(left,top,right-left,bottom-top);c.clip();
  if(band){c.fillStyle=band.color+'29';let segment=[];const fill=()=>{if(!segment.length)return;c.beginPath();segment.forEach((t,i)=>i?c.lineTo(x(t),y(t.channels[band.index].max)):c.moveTo(x(t),y(t.channels[band.index].max)));[...segment].reverse().forEach(t=>c.lineTo(x(t),y(t.channels[band.index].min)));c.closePath();c.fill();segment=[];};for(const t of history){if(segment.length&&t.elapsed_s-segment.at(-1).elapsed_s>.25)fill();segment.push(t);}fill();}
  for(const s of series){c.strokeStyle=s.color;c.lineWidth=2;c.setLineDash([]);c.beginPath();let previous=null;for(const t of history){if(!previous||t.elapsed_s-previous.elapsed_s>.25||t.stream_epoch!==previous.stream_epoch)c.moveTo(x(t),y(s.value(t)));else c.lineTo(x(t),y(s.value(t)));previous=t;}c.stroke();}
  c.strokeStyle='#6c7e8e';c.lineWidth=1;c.setLineDash([3,4]);
  for(const e of state?.events||[]){if(e.type!=='marker'||e.elapsed_s<last-30||e.elapsed_s>last)continue;const xx=x(e);c.beginPath();c.moveTo(xx,top);c.lineTo(xx,bottom);c.stroke();}
  c.restore();
}
function render(){
  if(!state)return;
  const since=performance.now()-lastSeen;
  if(isDemo)$('status').textContent='SIMULATED DATA · illustrative movement only · no hardware commands';
  else if(connected)$('status').textContent=!state.live||since>2500||!lastSeen?`${state.status}${state.data_age_s===null?'':` · last reading ${Math.round(state.data_age_s)} s ago`}`:'All three sensors live · graph and disk share the same readings';
  $('elapsed').textContent=timeLabel(state.elapsed_s+(state.active?(performance.now()-lastStateAt)/1000:0));
  if(document.hidden)return;
  const mode=$('compareMode').value,base=state.firmware?.calibrated?state.firmware.channels.map(c=>({amplitude:c.floor})):null;
  const selected=$('viewSensor').value,indices=['all','apart'].includes(selected)?[0,1,2]:[Number(selected)];
  const percent=['normalized','smoothed','desired'].includes(mode);
  $('compareHelp').textContent=percent?'Percent on matching axes. ADC range is measured from the noise floor to 970 counts. Smoothed output includes sensitivity and directional contrast; requested haptics also include ceiling and motor trim.':mode==='response'?'Envelope mean minus the saved opening threshold; raw readings remain unchanged.':mode==='peak'?'Highest short-window envelope within each telemetry period: brief events remain visible.':'Raw envelope readings on matching ADC-count axes. A0 = back · A1 = left · A2 = right.';
  const maximum=Number($('chartMaximum').value),fixed=!percent&&$('chartScale').value==='fixed'&&maximum>=1&&maximum<=1023;
  if(fixed)$('compareHelp').textContent+=` Fixed display range: 0–${maximum} counts. Values beyond the scale remain in the recording.`;
  const series=indices.map(i=>({color:colors[i],value:t=>{const c=t.channels[i];return mode==='response'?Math.max(0,c.mean-(base?.[i].amplitude||0)):c[mode];}}));
  let sharedMaximum=5;
  if(history.length){let low=Infinity,high=-Infinity;for(const t of history)for(const s of series){const v=s.value(t);low=Math.min(low,v);high=Math.max(high,v);}sharedMaximum=high+Math.max(1,(high-low)*.12);}
  const displayRange=[0,percent?100:fixed?maximum:sharedMaximum];
  if(selected==='apart')for(let i=0;i<3;i++)plot($('apartPlot'+i),[series[i]],{displayRange});
  else plot($('comparePlot'),series,{displayRange});
  const latest=history.at(-1);if(!latest)return;
  $('timing').textContent=(isDemo?'SIMULATED timing · ':'')+`${latest.rate.toLocaleString()} samples/s per sensor · ${latest.samples} samples each / ${(latest.window_us/1000).toFixed(2)} ms · largest sampling gap ${(latest.gap_us/1000).toFixed(2)} ms · ${latest.dropped} telemetry reports dropped · UART ${(latest.tx_us/1000).toFixed(2)} ms · ${latest.update_rate} motor commands/s total${latest.onset_latency_us?` · gate crossing to command complete ${(latest.onset_latency_us/1000).toFixed(2)} ms`:''}`;
  for(let i=0;i<3;i++){
    const channel=latest.channels[i];$('raw'+i).textContent=channel.raw;$('volts'+i).textContent=`≈ ${(channel.raw*5/1024).toFixed(3)} V at a 5 V reference`;
    $('p2p'+i).textContent=channel.p2p;$('amplitude'+i).textContent=channel.amplitude.toFixed(2);$('peak'+i).textContent=Math.max(...history.filter(t=>latest.elapsed_s-t.elapsed_s<=5).map(t=>t.channels[i].peak)).toFixed(2);
    $('range'+i).textContent=`Latest range ${channel.min}–${channel.max} · Mean ${channel.mean.toFixed(2)} counts${channel.max>=1021?' · Near upper ADC rail / possible clipping':''}`;
    const amplitude=channel.mean;$('response'+i).textContent=`Envelope mean ${amplitude.toFixed(2)}${base?` · Above quiet ${Math.max(0,amplitude-base[i].amplitude).toFixed(2)}`:''} ADC counts`;
    plot($('rawPlot'+i),[{color:colors[i],value:t=>t.channels[i].mean}],{band:{index:i,color:colors[i]},bounds:[0,1023]});
    plot($('variationPlot'+i),[{color:'#b75520',value:t=>t.channels[i].normalized},{color:'#6546a3',value:t=>t.channels[i].smoothed}],{displayRange:[0,100]});
    $('targetBar'+i).value=channel.desired;$('sentBar'+i).value=channel.sent;$('motorText'+i).textContent=`Requested ${channel.desired.toFixed(1)}% · issued effect ${channel.sent.toFixed(1)}%`;
  }
}
setInterval(render,80);
