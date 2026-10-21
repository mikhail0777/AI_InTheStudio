import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read=path=>readFileSync(new URL(path,import.meta.url),'utf8');

test('activity updates scroll only their own log container',()=>{
 const source=read('../src/components/AgentActivityFeed.tsx');
 assert.doesNotMatch(source,/scrollIntoView/);
 assert.match(source,/log\.scrollTop\s*=\s*log\.scrollHeight/);
 assert.match(source,/followLog/);
});

test('recording preview exposes playback controls and codec errors',()=>{
 const source=read('../src/RecordingApp.tsx');
 assert.match(source,/controls playsInline preload="metadata"/);
 assert.match(source,/role="alert"/);
 assert.match(source,/video codec that this browser cannot play/);
});

test('vehicle-only lookup fields are visible by default',()=>{
 const source=read('../src/components/TargetForm.tsx');
 assert.match(source,/<details className="form-section vehicle-details" open>/);
 assert.match(source,/Search without a plate/);
});

test('saved-sighting review exposes auditable multi-frame plate evidence',()=>{
 const source=read('../src/workspace/OperationalSightingsPage.tsx');
 assert.match(source,/getPlateAnalysis/);
 assert.match(source,/Multi-frame plate evidence/);
 assert.match(source,/Original crop/);
 assert.match(source,/Enhanced derivative/);
 assert.match(source,/Model confidence is evidence weighting, not measured accuracy/);
});
