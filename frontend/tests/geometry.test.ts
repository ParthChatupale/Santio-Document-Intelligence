import { test } from 'node:test';
import assert from 'node:assert/strict';
import { projectRect } from '../src/geometry.ts';

test('source rectangles respect PDF crop offsets and top-left display fractions', () => {
  const result = projectRect({left:.1,top:.2,right:.3,bottom:.4}, [10,20,210,120],
    {width:400,height:200,convertToViewportPoint:(x,y) => [(x-10)*2,(120-y)*2]});
  assert.deepEqual(result, {left:40,top:40,width:80,height:40});
});
test('rotated PDF viewport still produces a positive rectangle', () => {
  const result = projectRect({left:.1,top:.2,right:.3,bottom:.4}, [10,20,210,120],
    {width:200,height:400,convertToViewportPoint:(x,y) => [(y-20)*2,(x-10)*2]});
  assert.deepEqual(result, {left:120,top:40,width:40,height:80});
});
