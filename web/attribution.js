// Decides which face a piece of transcript belongs to.
//
// Two kinds of evidence:
//   lips   who was moving their mouth while those words were spoken (from the camera)
//   voice  the provider's speaker label for those words, if it gives one. Over time we
//          learn which label belongs to which face, and use that when lips are unclear.
// A learned voice wins brief ambiguous handoffs; sustained clear lips can correct it.
// No DOM in here, so it runs under Node for tests.

const DEFAULTS = {
  historyMs: 12000,
  visionLatencyMs: 50,   // GPU pipeline plus the shortened rolling score
  confident: 0.12,
  margin: 0.02,
  nearestMs: 100,       // never borrow a distant frame for missing audio history
  minLearnMs: 120,
  overrideMs: 250,
  silent: 0.03,
  bindVotes: 2,
  bindRatio: 1.4,
  voteDecay: 0.9,        // applied to a label's other choices on each new vote
};

export class Attributor {
  constructor(opts = {}) {
    this.o = { ...DEFAULTS, ...opts };
    this.frames = [];        // [{ t, scores: Map(faceId → score) }]
    this.votes = new Map();  // label → Map(faceId → weight)
    this.learnedUntil = new Map(); // don't count the same finalized audio twice
  }

  resetVoices() { this.votes.clear(); this.learnedUntil.clear(); }

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
    if (!span.length && this.frames.length && b - a <= this.o.nearestMs * 2) {
      const mid = (a + b) / 2; // span shorter than a frame: use the nearest one
      span = [this.frames.reduce((best, f) => (Math.abs(f.t - mid) < Math.abs(best.t - mid) ? f : best))];
      if (Math.abs(span[0].t - mid) > this.o.nearestMs) span = [];
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

  // Null means no face is visible; the caller drops that text. There is no global caption.
  attribute(startMs, endMs, label, learn = true) {
    const ranked = this.lipEvidence(startMs, endMs);
    const best = ranked[0], second = ranked[1];
    const hasLabel = label !== undefined && label !== null;
    const bound = hasLabel ? this.boundFace(label) : null;
    const clear = best && best.score >= this.o.confident && best.score - (second ? second.score : 0) >= this.o.margin;
    const duration = endMs - startMs;
    const canLearn = learn && duration >= this.o.minLearnMs && startMs >= (this.learnedUntil.get(label) ?? -Infinity);
    const vote = (id) => {
      if (!canLearn || !hasLabel) return;
      this._vote(label, id);
      this.learnedUntil.set(label, endMs);
    };

    // Mouth scores trail speech. At a quick handoff, the previous speaker can still
    // have the strongest score. Don't let that single short chunk move a known voice.
    const sustainedCorrection = clear && duration >= this.o.overrideMs &&
      best.score >= 0.65 && best.score - (second?.score || 0) >= 0.3 &&
      (ranked.find(f => f.id === bound)?.score || 0) < this.o.silent;
    if (bound !== null && (!clear || best.id !== bound) && !sustainedCorrection) {
      return { faceId: this.visibleIds().has(bound) ? bound : null, how: 'voice' };
    }

    if (clear) {
      vote(best.id);
      return { faceId: best.id, how: 'lips' };
    }
    if (hasLabel) {
      const bound = this.boundFace(label);
      if (bound !== null) {
        // Known voice. If their face is in view, caption it; if not, they're off-screen.
        return this.visibleIds().has(bound) ? { faceId: bound, how: 'voice' } : { faceId: null, how: 'voice' };
      }
    }
    // Never divert heard speech to a global subtitle when a face is visible. Weak lip
    // evidence is still more useful attached to the best candidate; finalized words and
    // learned voice labels can correct the provisional placement.
    if (best) {
      vote(best.id);
      return { faceId: best.id, how: 'best-visible' };
    }
    return { faceId: null, how: 'offscreen' };
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
