// Maps camera coordinates (0-1 of the camera frame) to screen pixels.
// Camera and display are both fixed to the wearer's head, so four numbers cover it:
// scale about the centre (sx, sy) and an offset (ox, oy). Saved in this browser.

const KEY = 'caption-glasses-calibration';
const IDENTITY = { sx: 1, sy: 1, ox: 0, oy: 0, mirror: false };
// The Pi camera sees ~66° across; the glasses show ~44°. So the camera image has to be
// blown up ~1.5x for a face to land where you actually see it. Nudge from here.
const XREAL_PRESET = { sx: 1.5, sy: 1.5, ox: 0, oy: 0.05, mirror: false };
const STEP_OFFSET = 0.01;
const STEP_SCALE = 0.03;

export class Calibration {
  constructor({ forceIdentity = false } = {}) {
    this.forceIdentity = forceIdentity; // live camera fills the screen, so no optical mapping
    this.videoAspect = 16 / 9;
    this.c = { ...IDENTITY };
    try { Object.assign(this.c, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch {}
    this.onChange = () => {};
  }

  // → [xPx, yPx]
  map(x, y) {
    if (this.forceIdentity) {
      const [left, top, width, height] = this._videoRect();
      return [left + x * width, top + y * height];
    }
    const c = this.forceIdentity ? IDENTITY : this.c;
    if (c.mirror) x = 1 - x;
    return [
      (0.5 + c.ox + c.sx * (x - 0.5)) * innerWidth,
      (0.5 + c.oy + c.sy * (y - 0.5)) * innerHeight,
    ];
  }

  // Sizes scale but don't shift.
  mapSize(w, h) {
    if (this.forceIdentity) {
      const [, , width, height] = this._videoRect();
      return [w * width, h * height];
    }
    const c = this.forceIdentity ? IDENTITY : this.c;
    return [c.sx * w * innerWidth, c.sy * h * innerHeight];
  }

  _videoRect() {
    const viewportAspect = innerWidth / innerHeight;
    if (viewportAspect > this.videoAspect) {
      const width = innerHeight * this.videoAspect;
      return [(innerWidth - width) / 2, 0, width, innerHeight];
    }
    const height = innerWidth / this.videoAspect;
    return [0, (innerHeight - height) / 2, innerWidth, height];
  }

  set(patch) {
    Object.assign(this.c, patch);
    try { localStorage.setItem(KEY, JSON.stringify(this.c)); } catch {}
    this.onChange();
  }

  nudge(what, dir) {
    const c = this.c;
    if (what === 'ox') this.set({ ox: c.ox + dir * STEP_OFFSET });
    else if (what === 'oy') this.set({ oy: c.oy + dir * STEP_OFFSET });
    else if (what === 'sx') this.set({ sx: Math.max(0.2, c.sx + dir * STEP_SCALE) });
    else if (what === 's') this.set({ sx: Math.max(0.2, c.sx + dir * STEP_SCALE), sy: Math.max(0.2, c.sy + dir * STEP_SCALE) });
  }

  preset() { this.set({ ...XREAL_PRESET, mirror: this.c.mirror }); }
  reset() { this.set({ ...IDENTITY }); }

  readout() {
    const c = this.c;
    const line = `scale ${c.sx.toFixed(2)} × ${c.sy.toFixed(2)}   offset ${c.ox.toFixed(2)}, ${c.oy.toFixed(2)}`;
    return this.forceIdentity ? `${line}\n(ignored while debug camera feed is on)` : line;
  }
}

export function bindCalibrationUi(cal, root) {
  const readout = root.querySelector('#cal-readout');
  const mirror = root.querySelector('#mirror-toggle');
  const refresh = () => { readout.textContent = cal.readout(); mirror.checked = cal.c.mirror; };
  cal.onChange = refresh;
  root.querySelectorAll('[data-cal]').forEach((b) => {
    b.addEventListener('click', () => cal.nudge(b.dataset.cal, Number(b.dataset.d)));
  });
  root.querySelector('#cal-preset').addEventListener('click', () => cal.preset());
  root.querySelector('#cal-reset').addEventListener('click', () => cal.reset());
  mirror.addEventListener('change', () => cal.set({ mirror: mirror.checked }));
  refresh();
}
