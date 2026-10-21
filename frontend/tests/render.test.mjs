import test from 'node:test';
import assert from 'node:assert/strict';
import {Writable} from 'node:stream';
import {createServer} from 'vite';
import React from 'react';
import {renderToPipeableStream} from 'react-dom/server';

test('authentication gate precedes the real workspace and routes remain explicit',async()=>{
 const previousLocation=globalThis.location,previousStorage=globalThis.localStorage;
 globalThis.localStorage={getItem:()=>null,setItem:()=>{}};
 globalThis.location={hash:'#/'};
 const server=await createServer({server:{middlewareMode:true},appType:'custom'});
 try{
  const {App}=await server.ssrLoadModule('/src/App.tsx');
  const {workspaceRoute}=await server.ssrLoadModule('/src/workspace/store.tsx');
  assert.equal(workspaceRoute('').source,'local');
  assert.equal(workspaceRoute('').view,'recording');
  assert.equal(workspaceRoute('#/search').source,'local');
  assert.equal(workspaceRoute('#/sample/search').source,'sample');
  assert.equal(workspaceRoute('#/sample/recording').source,'local');
  assert.equal(workspaceRoute('#/missing').view,'recording');
  const render=()=>new Promise((resolve,reject)=>{
   let html='';const output=new Writable({write(chunk,_encoding,done){html+=chunk.toString();done();}});
   output.on('finish',()=>resolve(html));output.on('error',reject);
   const stream=renderToPipeableStream(React.createElement(App),{onAllReady(){stream.pipe(output);},onError:reject});
  });
  const html=await render();
  assert.ok(html.includes('Loading LotTrace'));
  assert.ok(!html.includes('KJ72'));
  assert.ok(!html.includes('/demo/'));
 }finally{await server.close();globalThis.location=previousLocation;globalThis.localStorage=previousStorage;}
});
