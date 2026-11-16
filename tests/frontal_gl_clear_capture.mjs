// Diagnostic-only observation of actual clears, including SDK mask framebuffers.
// No getParameter/readback is added to the production render helper.
export function installGlClearCapture(gl) {
  const original = gl.clear, calls = [], framebufferIds = new WeakMap(); let nextId = 1;
  const framebufferId = value => { if (value === null) return 'canvas-default'; if (!framebufferIds.has(value)) framebufferIds.set(value, nextId++); return 'offscreen-' + framebufferIds.get(value); };
  const wrapper = function (...args) {
    const call = { sequence: calls.length + 1, bits: args[0], status: 'pending', observationErrors: [] }; calls.push(call);
    try {
      call.clearRGBA = Array.from(this.getParameter(this.COLOR_CLEAR_VALUE));
      call.framebuffer = framebufferId(this.getParameter(this.FRAMEBUFFER_BINDING));
      call.colorMask = Array.from(this.getParameter(this.COLOR_WRITEMASK));
      call.blendEnabled = this.isEnabled(this.BLEND);
    } catch (error) { call.observationErrors.push(String(error)); }
    try { const result = Reflect.apply(original, this, args); call.status = 'returned'; return result; }
    catch (error) { call.status = 'threw'; call.error = String(error); throw error; }
  };
  gl.clear = wrapper;
  return { all: () => structuredClone(calls), restore() { if (gl.clear === wrapper) gl.clear = original; } };
}
