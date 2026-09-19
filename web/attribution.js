// Decides which face a piece of transcript belongs to.
//
// Two kinds of evidence:
//   lips   who was moving their mouth while those words were spoken (from the camera)
//   voice  the provider's speaker label for those words, if it gives one. Over time we
//          learn which label belongs to which face, and use that when lips are unclear.
// Lips always win when they are clear. No DOM in here, so it runs under Node for tests.

export const NONE = 'none'; // pseudo-face: "nobody on camera was talking" (the wearer, or someone off-screen)

const DEFAULTS = {
  historyMs: 6000,
  visionLatencyMs: 250,  // camera → page delay plus the lag of the rolling speaking score
  confident: 0.40,       // mean speaking score for a clear lip result...
  margin: 0.15,          // ...and its lead over the runner-up
  weak: 0.25,            // below confident but still worth using if nothing better
  silent: 0.12,          // everyone below this = nobody on camera is talking
  bindVotes: 3,          // votes needed before a voice label is trusted
  bindRatio: 2,          // and its lead over the label's second choice
  voteDecay: 0.9,        // applied to a label's other choices on each new vote
};

export class Attributor {
  constructor(opts = {}) {
    this.o = { ...DEFAULTS, ...opts };
    this.frames = [];        // [{ t, scores: Map(faceId → score) }]
    this.votes = new Map();  // label → Map(faceId | NONE → weight)
  }

  addFrame(tMs, faces) {
    this.frames.push({ t: tMs, scores: new Map(faces.map((f) => [f.id, f.score])) });
    const cutoff = tMs - this.o.historyMs;
    while (this.frames.length && this.frames[0].t < cutoff) this.frames.shift();
  }

  visibleIds() {
    const last = this.frames[this.frames.length - 1];
    return last ? new Set(last.scores.keys()) : new Set();
  }

  // Mean speaking score per face over [startMs, endMs], best first.
  lipEvidence(startMs, endMs) {
    const a = startMs + this.o.visionLatencyMs;
    const b = endMs + this.o.visionLatencyMs;
    let span = this.frames.filter((f) => f.t >= a && f.t <= b);
    if (!span.length && this.frames.length) {
      const mid = (a + b) / 2; // span shorter than a frame: use the nearest one
      span = [this.frames.reduce((best, f) => (Math.abs(f.t - mid) < Math.abs(best.t - mid) ? f : best))];
    }
    const sum = new Map();
    for (const f of span) for (const [id, s] of f.scores) sum.set(id, (sum.get(id) || 0) + s);
    return [...sum].map(([id, s]) => ({ id, score: s / span.length })).sort((x, y) => y.score - x.score);
  }

  boundFace(label) {
    const v = this.votes.get(label);
    if (!v) return null;
    const ranked = [...v].sort((x, y) => y[1] - x[1]);
    const [top, second] = [ranked[0], ranked[1]];
    if (top[1] < this.o.bindVotes) return null;
    if (second && top[1] < second[1] * this.o.bindRatio) return null;
    return top[0];
  }

  _vote(label, faceId) {
    if (label === undefined || label === null) return;
    let v = this.votes.get(label);
    if (!v) this.votes.set(label, (v = new Map()));
    for (const [k, w] of v) if (k !== faceId) v.set(k, w * this.o.voteDecay);
    v.set(faceId, (v.get(faceId) || 0) + 1);
  }

  // → { faceId: id | null, how: 'lips' | 'voice' | 'weak' | 'none' }   (null = show in the bottom bar)
  attribute(startMs, endMs, label) {
    const ranked = this.lipEvidence(startMs, endMs);
    const best = ranked[0], second = ranked[1];
    const hasLabel = label !== undefined && label !== null;

    if (best && best.score >= this.o.confident && best.score - (second ? second.score : 0) >= this.o.margin) {
      this._vote(label, best.id);
      return { faceId: best.id, how: 'lips' };
    }
    if (!best || best.score < this.o.silent) this._vote(label, NONE);

    if (hasLabel) {
      const bound = this.boundFace(label);
      if (bound === NONE) return { faceId: null, how: 'voice' };
      if (bound !== null) {
        // Known voice. If their face is in view, caption it; if not, they're off-screen.
        return this.visibleIds().has(bound) ? { faceId: bound, how: 'voice' } : { faceId: null, how: 'voice' };
      }
    }
    if (best && best.score >= this.o.weak) return { faceId: best.id, how: 'weak' };
    return { faceId: null, how: 'none' };
  }

  // Split one transcript event into stretches by a single voice. Without word data it's one stretch.
  splitRuns(event) {
    if (!event.words || !event.words.length) {
      return [{ text: event.text, startMs: event.startMs, endMs: event.endMs, speaker: undefined }];
    }
    const runs = [];
    for (const w of event.words) {
      const last = runs[runs.length - 1];
      if (last && last.speaker === w.speaker) {
        last.text += ' ' + w.text;
        last.endMs = w.endMs;
      } else {
        runs.push({ text: w.text, startMs: w.startMs, endMs: w.endMs, speaker: w.speaker });
      }
    }
    return runs;
  }
}
