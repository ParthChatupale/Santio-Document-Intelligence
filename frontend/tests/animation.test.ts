import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AnimationClock, shouldAnimate } from '../src/animation.ts';

test('low frame rates preserve elapsed seconds instead of slowing the shader', () => {
  const clock = new AnimationClock();
  assert.equal(clock.tick(1000,true),0);
  assert.equal(clock.tick(2500,true),1.5);
  assert.equal(clock.tick(4500,true),3.5);
});

test('hidden or paused time does not advance the shader or jump on resume', () => {
  const clock = new AnimationClock();
  clock.tick(1000,true);
  clock.tick(2000,true);
  clock.pause();
  assert.equal(clock.tick(90000,true),1);
  assert.equal(clock.tick(91000,true),2);
  assert.equal(clock.tick(92000,false),2);
  assert.equal(clock.tick(200000,true),2);
});

test('reduced motion applies by default and explicit play/pause takes precedence', () => {
  assert.equal(shouldAnimate('system',true),false);
  assert.equal(shouldAnimate('system',false),true);
  assert.equal(shouldAnimate('on',true),true);
  assert.equal(shouldAnimate('off',false),false);
});
