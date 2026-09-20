import test from 'node:test';
import assert from 'node:assert/strict';
import '../web/stt/mic-test.js';
import { createProvider } from '../web/stt/provider.js';

test('mic-test requires a live microphone and never transcribes or uploads it', async () => {
  const statuses = [];
  const provider = createProvider('mic-test', {
    onStatus: status => statuses.push(status),
    onTranscript: () => assert.fail('mic-test must not emit transcripts'),
  });

  assert.equal(provider.needsMic, true);
  await assert.rejects(provider.start(null), /no live microphone track/);
  await assert.rejects(
    provider.start({ getAudioTracks: () => [{ readyState: 'ended' }] }),
    /no live microphone track/,
  );

  await provider.start({ getAudioTracks: () => [{ readyState: 'live' }] });
  assert.match(statuses.at(-1), /mic test running/);
  provider.stop();
  assert.equal(statuses.at(-1), 'stopped');
});
