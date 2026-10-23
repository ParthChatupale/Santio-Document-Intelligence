import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AnimationClock, BACKGROUND_FPS, drawingSize, FrameLimiter, shouldAnimate } from '../src/animation.ts';

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

test('system reduced motion and busy/dialog state each stop decorative animation', () => {
  assert.equal(shouldAnimate(false,false),true);
  assert.equal(shouldAnimate(true,false),false);
  assert.equal(shouldAnimate(false,true),false);
  assert.equal(shouldAnimate(true,true),false);
});

test('drawing buffers stay within the pixel budget on high-DPI and ultrawide screens', () => {
  for (const [w,h,dpr] of [[1500,450,2],[3840,600,3],[320,400,4]]) {
    const [width,height] = drawingSize(w,h,dpr);
    assert.ok(width*height <= 600_000);
    assert.ok(width <= w && height <= h);
  }
});

test('GPU frame limit applies across display refresh rates and resets on resume', () => {
  for (const hz of [60,120,144]) {
    const limiter = new FrameLimiter();
    let draws = 0;
    for (let tick=0; tick<hz*10; tick++) if (limiter.shouldRender(tick*1000/hz)) draws++;
    assert.ok(draws <= BACKGROUND_FPS*10+1, `${hz}Hz: ${draws} draws`);
    assert.ok(draws >= BACKGROUND_FPS*10-2, `${hz}Hz: ${draws} draws`);
    limiter.reset();
    assert.equal(limiter.shouldRender(10000),true);
    assert.equal(limiter.shouldRender(10001),false);
  }
});
