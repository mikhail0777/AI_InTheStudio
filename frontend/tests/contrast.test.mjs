import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css=readFileSync(new URL('../src/operational.css',import.meta.url),'utf8');
const token=name=>{
 const value=css.match(new RegExp(`--${name}:\\s*(#[\\da-f]{6})`,'i'))?.[1];
 assert.ok(value,`Missing semantic colour: ${name}`);
 return value;
};
const luminance=hex=>{
 const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255)
  .map(v=>v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4);
 return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;
};
const contrast=(a,b)=>{
 const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);
 return (values[0]+0.05)/(values[1]+0.05);
};
test('operational text and primary actions meet AA contrast',()=>{
 for(const colour of ['ink','muted','blue']){
  assert.ok(contrast(token(colour),'#ffffff')>=4.5,colour);
  assert.ok(contrast(token(colour),'#f6f6f3')>=4.5,`${colour} on workspace`);
 }
 assert.ok(contrast(token('disabled-text'),token('disabled-bg'))>=4.5);
});
test('form boundaries meet non-text contrast on white and warm surfaces',()=>{
 assert.ok(contrast(token('field-border'),'#ffffff')>=3);
 assert.ok(contrast(token('field-border'),'#f6f6f3')>=3);
});
