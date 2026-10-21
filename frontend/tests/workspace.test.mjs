import test from 'node:test';
import assert from 'node:assert/strict';
import {applyAction,emptyFilters,initialState,parseStoredState,plateMatches,searchSightings,vehicles} from '../src/workspace/model.ts';

test('partial and uncertain plate readings match without declaring identity',()=>{
 assert.equal(plateMatches('KJ72 XLM','kj72'),true);
 assert.equal(plateMatches('BC42 R?V','BC42 RNV'),true);
 assert.equal(plateMatches('KJ72 H?G','KJ72 HZG'),true);
 assert.equal(plateMatches('KJ72 XLM','BC42'),false);
 assert.equal(plateMatches('KJ72 XLM','KJ72 XLMA'),false);
 assert.equal(searchSightings(initialState().sightings,{...emptyFilters,query:'KJ72'}).length,7);
});
test('camera, movement, attributes and date filters compose',()=>{
 const results=searchSightings(initialState().sightings,{...emptyFilters,query:'KJ72',camera:'Main entrance',direction:'Arrival',colour:'White',make:'BMW',model:'3 Series',from:'2026-10-19',to:'2026-10-19'});
 assert.deepEqual(results.map(s=>s.id),['7843']);
 assert.equal(searchSightings(initialState().sightings,{...emptyFilters,from:'2026-10-20',to:'2026-10-18'}).length,0);
});
test('sorting is stable by time and fixtures do not invent confidence',()=>{
 const rows=initialState().sightings;
 assert.equal(searchSightings(rows,{...emptyFilters,sort:'newest'})[0].id,'7848');
 assert.equal(searchSightings(rows,{...emptyFilters,sort:'oldest'})[0].id,'7838');
 assert.ok(rows.every(row=>!('confidence' in row)));
});
test('verify then correct retains original OCR and reopens review',()=>{
 const seed=initialState();
 const confirmed=applyAction(seed,{type:'review',id:'7844',status:'confirmed'},'staff','2026-10-19T20:00:00','a');
 assert.equal(confirmed.sightings.find(s=>s.id==='7844').status,'confirmed');
 const corrected=applyAction(confirmed,{type:'correct',id:'7844',plate:'KJ72 HZG',reason:'Read Z in enlarged source frame'},'staff','2026-10-19T20:01:00','b');
 const row=corrected.sightings.find(s=>s.id==='7844');
 assert.equal(row.plate,'KJ72 HZG');assert.equal(row.originalPlate,'KJ72 H?G');assert.equal(row.status,'pending');
 assert.equal(corrected.log.length,2);assert.match(corrected.log[0].text,/Read Z/);
 assert.equal(seed.log.length,0);assert.equal(seed.sightings.find(s=>s.id==='7844').plate,'KJ72 H?G');
});
test('invalid corrections do not mutate records',()=>{
 const seed=initialState();
 assert.throws(()=>applyAction(seed,{type:'correct',id:'7842',plate:'!',reason:'bad'},'staff'));
 assert.throws(()=>applyAction(seed,{type:'correct',id:'7842',plate:'KJ72 XLM',reason:' '},'staff'));
 assert.equal(seed.log.length,0);
});
test('link preserves observed attributes, original reading and source image',()=>{
 const seed=initialState();const before=seed.sightings[0];
 const next=applyAction(seed,{type:'link',id:before.id,vehicleId:'bmw'},'staff');const after=next.sightings[0];
 assert.equal(after.vehicleId,'bmw');assert.deepEqual(after.observed,before.observed);assert.deepEqual(after.image,before.image);assert.equal(after.originalPlate,before.originalPlate);assert.equal(after.status,'pending');
 assert.throws(()=>applyAction(seed,{type:'link',id:before.id,vehicleId:'missing'},'staff'));
});
test('unrelated sightings can be reopened',()=>{
 const rejected=applyAction(initialState(),{type:'review',id:'7842',status:'unrelated'},'staff');
 const reopened=applyAction(rejected,{type:'review',id:'7842',status:'pending'},'staff');
 assert.equal(reopened.sightings[0].status,'pending');assert.equal(reopened.log.length,2);
});
test('only demo managers can complete review; flags reopen it',()=>{
 assert.throws(()=>applyAction(initialState(),{type:'approve'},'staff'),/Manager/);
 const approved=applyAction(initialState(),{type:'approve'},'manager');
 assert.equal(approved.incident,'reviewed');assert.match(approved.log[0].actor,/Manager/);
 const flagged=applyAction(approved,{type:'flag',text:'Additional mark for review'},'staff');
 assert.equal(flagged.incident,'open');assert.equal(flagged.notes.at(-1).text,'Additional mark for review');
});
test('notes retain actor and timestamp',()=>{
 const next=applyAction(initialState(),{type:'note',text:'Only the pale mark is visible'},'staff','2026-10-19T20:00:00','test-note');
 assert.equal(next.notes.at(-1).at,'2026-10-19T20:00:00');assert.match(next.notes.at(-1).actor,/Staff/);
 assert.equal(next.log[0].vehicleId,'range');
});
test('demo storage round trip and corrupted storage recovery',()=>{
 const next=applyAction(initialState(),{type:'review',id:'7842',status:'confirmed'},'staff');
 assert.deepEqual(parseStoredState(JSON.stringify(next)),next);
 assert.equal(parseStoredState('{invalid').sightings.length,10);
 assert.equal(parseStoredState('{}').version,2);
 assert.equal(parseStoredState(null).version,2);
 const unsafe={...next,sightings:next.sightings.map(s=>({...s,image:{file:'https://untrusted.example/image',region:[0,0,1,1]}}))};
 assert.equal(parseStoredState(JSON.stringify(unsafe)).sightings[0].image.file,'/demo/dealership.png');
 const oldConfidence={...next,sightings:next.sightings.map(s=>({...s,confidence:96}))};
 assert.ok(parseStoredState(JSON.stringify(oldConfidence)).sightings.every(s=>!('confidence' in s)));
});
