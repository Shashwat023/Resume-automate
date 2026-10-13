/** Pure input-mapping helpers for the Live View ("Take Control") surface. */

export interface Viewport {
  width: number;
  height: number;
}

interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Map a pointer position on the rendered <img> to the page's CSS-pixel
 * coordinates. `viewport` is the real page size reported by the screencast
 * (deviceWidth/deviceHeight); the JPEG itself may be scaled down, so using its
 * natural size would land clicks off-target. Falls back to the natural size.
 */
export function mapPointToViewport(
  clientX: number,
  clientY: number,
  rect: RectLike,
  natural: Viewport,
  viewport?: Partial<Viewport> | null
): { x: number; y: number } {
  const targetWidth = viewport?.width || natural.width;
  const targetHeight = viewport?.height || natural.height;
  return {
    x: ((clientX - rect.left) / rect.width) * targetWidth,
    y: ((clientY - rect.top) / rect.height) * targetHeight,
  };
}

// Chrome ignores editing/navigation keys sent without a virtual key code.
const KEY_CODES: Record<string, number> = {
  Backspace: 8,
  Tab: 9,
  Enter: 13,
  Escape: 27,
  ' ': 32,
  PageUp: 33,
  PageDown: 34,
  End: 35,
  Home: 36,
  ArrowLeft: 37,
  ArrowUp: 38,
  ArrowRight: 39,
  ArrowDown: 40,
  Delete: 46,
};

interface KeyLike {
  key: string;
  code: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  metaKey: boolean;
}

export function keyModifiers(e: Pick<KeyLike, 'altKey' | 'ctrlKey' | 'metaKey' | 'shiftKey'>) {
  // CDP bitmask: Alt=1, Ctrl=2, Meta=4, Shift=8.
  return (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0);
}

export function buildKeyMessage(eventType: 'keyDown' | 'keyUp', e: KeyLike) {
  const keyCode =
    KEY_CODES[e.key] ??
    (e.key.length === 1 ? e.key.toUpperCase().charCodeAt(0) : undefined);
  const modifiers = keyModifiers(e);
  // Printable text only when no Ctrl/Alt/Meta chord is held.
  const printable = e.key.length === 1 && !(modifiers & (1 | 2 | 4));
  return {
    type: 'key' as const,
    event: eventType,
    key: e.key,
    code: e.code || undefined,
    keyCode,
    modifiers: modifiers || undefined,
    text: eventType === 'keyDown' && printable ? e.key : undefined,
  };
}
