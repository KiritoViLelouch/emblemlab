import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../app/lux-policy.ts',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2017}});
const {luxForms,luxConstraints}=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'));
const catalog=JSON.parse(fs.readFileSync(new URL('../../../data/catalogs/tft/set18_18_4.json',import.meta.url),'utf8'));
const forms=luxForms(catalog);
test('exact reviewed Set 18 Lux identities and real cost',()=>{
 assert.equal(forms.length,9);assert.ok(forms.every(c=>c.cost===5&&c.exclusive_group==='DA_18_Lux'));
 assert.deepEqual(luxForms({...catalog,game:'JCC'}),[]);
 assert.deepEqual(luxForms({...catalog,id:'other_patch'}),[]);
});
test('without excludes every available form and preserves non-Lux constraints',()=>{
 const r=luxConstraints(catalog,'without',['DA_18_Akali_AD',forms[0].id],['DA_18_Ornn'],5);
 assert.deepEqual(r.locked_units,['DA_18_Akali_AD']);assert.ok(forms.every(c=>r.banned_units.includes(c.id)));
 assert.ok(r.banned_units.includes('DA_18_Ornn'));
});
test('with a chosen form locks exactly it and bans alternatives',()=>{
 const r=luxConstraints(catalog,forms[2].id,[],[],5);
 assert.deepEqual(r.locked_units,[forms[2].id]);assert.equal(r.banned_units.length,8);
 assert.ok(!r.banned_units.includes(forms[2].id));
});
test('rejects unknown form and cost contradiction',()=>{
 assert.throws(()=>luxConstraints(catalog,'fabricated',[],[],5));
 assert.throws(()=>luxConstraints(catalog,forms[0].id,[],[],4),/五费/);
});
test('other games retain original constraints',()=>{
 assert.deepEqual(luxConstraints({...catalog,game:'JCC'},'without',['u'],['v'],3),{locked_units:['u'],banned_units:['v'],max_unit_cost:3});
});
