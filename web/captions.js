// Transcript state is separate from drawing. A final often covers only the first
// part of an interim; preserve the remainder until the next interim replaces it.
export class CaptionBuffer {
  constructor() { this.reset(); }
  reset() { this.finals = new Map(); this.partial = []; this.finalEnd = -Infinity; this.updated = new Map(); }

  update(event, runs, now) {
    for (const run of runs) {
      if (!run.text) continue;
      const key = run.faceId ?? 'bar';
      if (now - (this.updated.get(key) ?? -Infinity) > 4000) this.finals.delete(key);
      this.updated.set(key, now);
    }
    if (!event.isFinal) {
      this.partial = runs.filter(r => r.endMs > this.finalEnd + 1);
    } else {
      for (const run of runs) {
        if (!run.text || run.endMs <= this.finalEnd + 1) continue;
        const key = run.faceId ?? 'bar';
        let previous = this.finals.get(key);
        if (!previous) previous = { text: '', updated: now };
        this.finals.set(key, { text: `${previous.text} ${run.text}`.trim(), updated: now });
      }
      this.finalEnd = Math.max(this.finalEnd, event.endMs, ...runs.map(r => r.endMs));
      this.partial = this.partial.flatMap(run => {
        if (run.endMs <= this.finalEnd + 1) return [];
        if (run.startMs >= this.finalEnd) return [run];
        const words = run.words?.filter(w => w.endMs > this.finalEnd + 1);
        if (!words?.length) return [];
        return [{ ...run, words, text: words.map(w => w.text).join(' '), startMs: words[0].startMs }];
      });
    }
  }

  textFor(key) {
    const final = this.finals.get(key);
    return [final?.text || '',
      ...this.partial.filter(r => (r.faceId ?? 'bar') === key).map(r => r.text)].filter(Boolean).join(' ');
  }

  compact(key, maxWidth, measure) {
    const final = this.finals.get(key);
    if (final?.text.length > 2048) {
      // Trim only at measured line boundaries so a long conversation remains
      // bounded without shifting the words currently on screen.
      final.text = captionLines(final.text, maxWidth, measure, 8).replaceAll('\n', ' ');
    }
  }
}

// Wrap left to right and retain complete lines; adding a word doesn't rebalance
// the preceding lines. The caller supplies the actual font's pixel measurement.
export function captionLines(text, maxWidth, measure, keepLines = 2) {
  const lines = [];
  let line = '';
  for (const word of text.trim().split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word;
    if (line && measure(next) > maxWidth) { lines.push(line); line = word; }
    else line = next;
  }
  if (line) lines.push(line);
  return lines.slice(-keepLines).join('\n');
}

// Dead zone removes camera jitter. Larger movements are followed over ~180 ms,
// independent of the monitor's refresh rate.
export function smoothAnchor(previous, x, y, dt) {
  if (!previous || Math.hypot(x - previous.x, y - previous.y) > 200) return { x, y };
  const distance = Math.hypot(x - previous.x, y - previous.y);
  if (distance <= 8) return previous;
  const alpha = (1 - Math.exp(-dt / 180)) * (distance - 8) / distance;
  return { x: previous.x + (x - previous.x) * alpha, y: previous.y + (y - previous.y) * alpha };
}
