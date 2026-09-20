// Synthetic display demo only. No serial, fetch, EEPROM, or motor commands.
// The same fixed Rev 3 mapping, integrated in 5 ms steps; no measured timing.
const floor=[10,12,11],smoothed=[0,0,0];
let previous=0;
const clamp=x=>Math.max(0,Math.min(1,x));
function levels(t){
  const phase=t%24;
  if(phase<3||phase>22)return [0,0,0];
  if(phase>19)return [960,958,959];
  const angle=(phase-3)/16*Math.PI*2;
  return [Math.PI,Math.PI*1.6,Math.PI*.4].map(offset=>
    8+70*Math.pow((1+Math.cos(angle-offset))/2,4));
}
export function simulatedFrame(t,seq){
  if(t<previous){previous=t;smoothed.fill(0);}
  // A hidden tab can skip time. Bound catch-up instead of building a queue.
  let at=Math.max(previous,t-.2),excess=levels(t),normalized=[];
  while(at<t){
    const dt=Math.min(.005,t-at);at+=dt;excess=levels(at);
    const loudest=Math.max(...excess);
    normalized=excess.map((x,i)=>clamp(x/(970-floor[i])));
    for(let i=0;i<3;i++){
      const n=normalized[i];
      const target=n?Math.pow(n,.4)*Math.pow(clamp(excess[i]/loudest),1.5*(1-n)**2):0;
      if(!n)smoothed[i]=0;
      else smoothed[i]+=(target-smoothed[i])*dt/((target>smoothed[i]?.005:.05)+dt);
      if(target===1&&smoothed[i]>.999)smoothed[i]=1;
    }
  }
  previous=t;
  if(!normalized.length)normalized=excess.map((x,i)=>clamp(x/(970-floor[i])));
  const channels=excess.map((x,i)=>{
    const mean=Math.min(1023,floor[i]+x),n=normalized[i]*100,s=smoothed[i]*100;
    return {raw:Math.round(mean),min:Math.max(0,Math.floor(mean)-1),max:Math.min(1023,Math.ceil(mean)+1),mean,amplitude:mean,peak:mean+1,p2p:2,normalized:n,smoothed:s,desired:s,sent:s,floor:floor[i],close:floor[i]-1,reference:970,rail:false};
  });
  return {version:3,seq,device_ms:Math.round(t*1000),elapsed_s:t,window_us:40000,samples:50,rate:1250,gap_us:0,tx_us:0,onset_latency_us:0,update_rate:0,dropped:0,stream_epoch:0,missing_windows:0,flags:5,calibrated:true,qualified:true,muted:false,saving:false,quiet_ready:false,probing:false,phase:0,progress:0,profile:21,ceiling:100,test_mask:15,trims:[100,100,100],command_sequence:0,channels};
}
