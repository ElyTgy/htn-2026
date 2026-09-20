import assert from 'node:assert/strict';
import {simulatedFrame} from '../dashboard/simulation.mjs';
let full=false,directional=false;
for(let seq=1;seq<=600;seq++){
  const t=seq*.04,frame=simulatedFrame(t,seq);
  assert.equal(frame.version,3);assert.equal(frame.ceiling,100);
  for(const c of frame.channels){
    assert(c.raw>=c.min&&c.raw<=c.max&&c.max<=1023);
    assert(c.desired>=0&&c.desired<=100);
    if(t<3||t>22)assert.equal(c.desired,0);
  }
  if(t>20&&t<21){assert(frame.channels.every(c=>c.desired===100));full=true;}
  if(t>4&&t<18&&Math.max(...frame.channels.map(c=>c.desired))-Math.min(...frame.channels.map(c=>c.desired))>15)directional=true;
}
assert(full&&directional);
console.log('PASS: Rev 3 simulation shows silence, directional movement and near-rail full output');
