import { describe, expect, it } from 'vitest';
import { buildKeyMessage, mapPointToViewport } from './liveViewInput';

const key = (over: Partial<Parameters<typeof buildKeyMessage>[1]>) => ({
  key: 'a',
  code: 'KeyA',
  shiftKey: false,
  ctrlKey: false,
  altKey: false,
  metaKey: false,
  ...over,
});

describe('mapPointToViewport', () => {
  const rect = { left: 10, top: 20, width: 640, height: 400 };

  it('uses the reported viewport rather than the scaled image size', () => {
    const point = mapPointToViewport(330, 220, rect, { width: 1280, height: 800 }, {
      width: 1920,
      height: 1200,
    });
    expect(point).toEqual({ x: 960, y: 600 });
  });

  it('falls back to the natural image size without metadata', () => {
    const point = mapPointToViewport(330, 220, rect, { width: 1280, height: 800 });
    expect(point).toEqual({ x: 640, y: 400 });
  });
});

describe('buildKeyMessage', () => {
  it('sends a virtual key code for Backspace and Enter', () => {
    expect(buildKeyMessage('keyDown', key({ key: 'Backspace', code: 'Backspace' })).keyCode).toBe(8);
    expect(buildKeyMessage('keyDown', key({ key: 'Enter', code: 'Enter' })).keyCode).toBe(13);
  });

  it('sends text for a printable key only on keyDown', () => {
    expect(buildKeyMessage('keyDown', key({})).text).toBe('a');
    expect(buildKeyMessage('keyUp', key({})).text).toBeUndefined();
  });

  it('does not send text for a Ctrl chord and encodes modifiers', () => {
    const message = buildKeyMessage('keyDown', key({ key: 'v', ctrlKey: true }));
    expect(message.text).toBeUndefined();
    expect(message.modifiers).toBe(2);
  });
});
