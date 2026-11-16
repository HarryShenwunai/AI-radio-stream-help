import test from 'node:test';
import assert from 'node:assert/strict';
import { renderTransparentFrame } from '../frontend/live2d-renderer.mjs';
import { installGlClearCapture } from './frontal_gl_clear_capture.mjs';
function fixture() {
  const state = { rgba: [0, 0, 0, 0], framebuffer: null, order: [] }, mask = {}, result = {};
  const gl = { COLOR_CLEAR_VALUE: 1, FRAMEBUFFER_BINDING: 2, COLOR_WRITEMASK: 3, BLEND: 4,
    getParameter(key) { return key === 1 ? state.rgba : key === 2 ? state.framebuffer : [true, true, true, true]; },
    isEnabled() { return true; }, clearColor(...rgba) { state.rgba = rgba; state.order.push('clearColor'); },
    clear() { state.order.push('clear'); return result; } };
  const capture = installGlClearCapture(gl);
  const renderer = { gl, render(stage) { assert.equal(stage, result); assert.equal(this, renderer); gl.clear(16384); state.framebuffer = mask; gl.clearColor(1, 1, 1, 0); gl.clear(16384); state.framebuffer = null; return result; } };
  return { state, gl, capture, renderer, stage: result };
}
function verifyCanvas(trace) { for (const row of trace.filter(r => r.framebuffer === 'canvas-default')) assert.deepEqual(row.clearRGBA, [0, 0, 0, 0]); }
test('two frames clear canvas to transparent black despite SDK mask leaving transparent white', () => {
  const f = fixture(); assert.equal(renderTransparentFrame(f.renderer, f.stage), f.stage); renderTransparentFrame(f.renderer, f.stage);
  const trace = f.capture.all(); verifyCanvas(trace); assert.equal(trace.length, 4);
  assert.deepEqual(trace.filter(r => r.framebuffer !== 'canvas-default').map(r => r.clearRGBA), [[1, 1, 1, 0], [1, 1, 1, 0]]);
  assert.equal(f.state.order[0], 'clearColor');
});
test('known-bad rendering without clear is rejected on the second frame', () => {
  const f = fixture(); f.renderer.render(f.stage); f.renderer.render(f.stage);
  assert.throws(() => verifyCanvas(f.capture.all()));
  assert.deepEqual(f.capture.all()[2].clearRGBA, [1, 1, 1, 0]);
});
test('helper and diagnostic wrapper preserve return, receiver and original exception', () => {
  const f = fixture(), sentinel = new Error('actual GL failure'); let receiver;
  f.gl.clear = function () { receiver = this; throw sentinel; };
  const capture = installGlClearCapture(f.gl);
  assert.throws(() => renderTransparentFrame(f.renderer, f.stage), error => error === sentinel);
  assert.equal(receiver, f.gl); assert.equal(capture.all()[0].status, 'threw');
  assert.deepEqual(capture.all()[0].clearRGBA, [0, 0, 0, 0]);
});
