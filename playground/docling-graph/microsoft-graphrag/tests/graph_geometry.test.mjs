import { test } from 'node:test';
import assert from 'node:assert/strict';
import { initialise, stepLayout, fitCamera, curve, curvePoint, curveDistance, assertionDirections, graphCounts, radius, citedRecords } from '../web/graph-geometry.js';

const nodes=()=>[
  {id:'method',label:'METHOD A',community:0,degree:3},
  {id:'dataset',label:'DATA B',community:1,degree:1},
  {id:'tool',label:'TOOL C',community:0,degree:2},
];
const edges=[{id:'one',source:'method',target:'dataset'},{id:'two',source:'method',target:'tool'}];

test('layout is repeatable and keeps every entity and original connection',()=>{
  const a=nodes(),b=nodes();initialise(a);initialise(b);
  for(const set of [a,b])for(let i=0;i<150;i++)stepLayout(set,edges,new Map(set.map(n=>[n.id,n])),.7);
  assert.deepEqual(a,b);
  assert.deepEqual(a.map(n=>n.id),nodes().map(n=>n.id));
  for(const n of a)assert.ok(Number.isFinite(n.x)&&Number.isFinite(n.y));
  assert.deepEqual(graphCounts(a,edges,new Set(a.map(n=>n.id))),{nodes:3,edges:2});
});

test('initial positions are stable across input order and pinned positions survive settling',()=>{
  const a=nodes(),b=nodes().reverse();initialise(a);initialise(b);
  for(const n of a){const other=b.find(v=>v.id===n.id);assert.equal(n.x,other.x);assert.equal(n.y,other.y);}
  const n=a[0];n.pinned=true;const position=[n.x,n.y];stepLayout(a,edges,new Map(a.map(n=>[n.id,n])));
  assert.deepEqual([n.x,n.y],position);
});

test('native undirected endpoint order never creates an assertion arrow',()=>{
  const lookup=new Map(nodes().map(n=>[n.id,n]));
  const edge={source:'dataset',target:'method'};
  assert.deepEqual(assertionDirections(edge,lookup),[]);
  assert.deepEqual(assertionDirections({...edge,assertion_evidence:[{source:'Method A',target:'Data B'}]},lookup),[-1]);
  assert.deepEqual(assertionDirections({...edge,assertion_evidence:[{source:'Different method',target:'Data B'}]},lookup),[]);
  assert.deepEqual(assertionDirections({...edge,assertion_evidence:[{source:'Data B',target:'Method A'},{source:'METHOD_A',target:'DATA B'}]},lookup),[1,-1]);
});

test('curved connection picking follows the visible curve, including loops',()=>{
  const g=curve({x:0,y:0},{x:200,y:0},'connection');
  assert.ok(curveDistance(g,curvePoint(g,.5))<.05);
  assert.ok(curveDistance(g,{x:100,y:100})>70);
  const loop=curve({x:5,y:5},{x:5,y:5},'loop');
  assert.ok(curveDistance(loop,curvePoint(loop,.5))<.05);
});

test('fit camera frames all positions inside the unobstructed canvas area',()=>{
  const ns=[{x:-500,y:-200},{x:700,y:600}],bounds={x:280,y:130,width:800,height:500};
  const c=fitCamera(ns,bounds);
  for(const n of ns){const x=n.x*c.k+c.x,y=n.y*c.k+c.y;assert.ok(x>=bounds.x&&x<=bounds.x+bounds.width);assert.ok(y>=bounds.y&&y<=bounds.y+bounds.height);}
  assert.deepEqual(fitCamera([],bounds),{x:0,y:0,k:1});
});

test('filters count only connections whose endpoints are visible',()=>{
  assert.deepEqual(graphCounts(nodes(),edges,new Set(['method','tool'])),{nodes:2,edges:1});
  assert.deepEqual(graphCounts(nodes(),edges,new Set()),{nodes:0,edges:0});
});

test('connectivity sizing is bounded, including a very high-degree hub',()=>{
  assert.ok(radius({degree:100000},1)<15);
  assert.ok(radius({degree:100000},5)<24);
  assert.ok(radius({degree:0},.04)>=3);
  assert.ok(radius({degree:4},1)>radius({degree:1},1));
});

test('answer highlighting excludes retrieved but uncited graph records',()=>{
  const evidence={entities:[{citation_id:26,native_id:'dino'},{citation_id:27,native_id:'uncited'}],relationships:[{citation_id:307,native_id:'link'}]};
  assert.deepEqual(citedRecords('A claim [Data: Entities (26); Relationships (307); Sources (111)]',evidence),{nodes:['dino'],edges:['link']});
  assert.deepEqual(citedRecords('An answer without graph citations.',evidence),{nodes:[],edges:[]});
});
