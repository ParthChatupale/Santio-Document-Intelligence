import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AnimationClock, artworkResolution, shouldAnimate } from '../src/animation.ts';

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

test('artwork preserves small panel resolution and bounds large panels', () => {
  assert.deepEqual(artworkResolution(420,300), {width:420, height:300});
  for (const [width,height] of [[1920,1080],[3840,2160],[300,1600]]) {
    const size = artworkResolution(width,height);
    assert.ok(size.width * size.height <= 240_000);
    assert.ok(Math.abs(size.width / size.height - width / height) < .01);
  }
  assert.deepEqual(artworkResolution(0,0), {width:1, height:1});
});
