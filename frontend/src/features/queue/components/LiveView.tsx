import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { wsUrl } from '@/lib/wsUrl';

interface LiveViewProps {
  applicationId: string;
  onClose: () => void;
}

/**
 * Canvas + input capture over WS /ws/apply/{id}/live-view — the one
 * remaining human-in-the-loop surface (Day 4 scope correction: 2FA only,
 * plus a CAPTCHA-solve-failed escalation). Backend sends JPEG screencast
 * frames and forwards raw CDP Input.dispatch{Mouse,Key}Event params, so
 * this component only needs to scale click coordinates from the rendered
 * <img> size to the frame's natural (real viewport) size and pass key
 * events straight through.
 */
export const LiveView = ({ applicationId, onClose }: LiveViewProps) => {
  const imgRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(wsUrl(`/ws/apply/${applicationId}/live-view`));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'frame') {
        setFrameSrc(`data:image/jpeg;base64,${msg.data}`);
      }
    };
    return () => ws.close();
  }, [applicationId]);

  const sendMouse = (eventType: string, e: React.MouseEvent<HTMLImageElement>) => {
    const img = imgRef.current;
    const ws = wsRef.current;
    if (!img || !img.naturalWidth || !ws || ws.readyState !== WebSocket.OPEN) return;
    const rect = img.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * img.naturalWidth;
    const y = ((e.clientY - rect.top) / rect.height) * img.naturalHeight;
    ws.send(JSON.stringify({ type: 'mouse', event: eventType, x, y, button: 'left' }));
  };

  const sendKey = (eventType: 'keyDown' | 'keyUp', e: React.KeyboardEvent) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    e.preventDefault();
    ws.send(
      JSON.stringify({
        type: 'key',
        event: eventType,
        key: e.key,
        text: eventType === 'keyDown' && e.key.length === 1 ? e.key : undefined,
      })
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-4xl flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-gray-400'}`}
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              Live Browser — Take Control
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            aria-label="Close live view"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div
          className="flex-1 overflow-auto bg-gray-900 flex items-center justify-center p-2 outline-none"
          tabIndex={0}
          onKeyDown={(e) => sendKey('keyDown', e)}
          onKeyUp={(e) => sendKey('keyUp', e)}
        >
          {frameSrc ? (
            <img
              ref={imgRef}
              src={frameSrc}
              alt="Live browser view"
              className="max-w-full max-h-full cursor-pointer select-none"
              draggable={false}
              onMouseDown={(e) => sendMouse('mousePressed', e)}
              onMouseUp={(e) => sendMouse('mouseReleased', e)}
              onMouseMove={(e) => sendMouse('mouseMoved', e)}
            />
          ) : (
            <p className="text-gray-400 text-sm">Waiting for the browser feed...</p>
          )}
        </div>

        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 shrink-0">
          Click into the browser above and enter your verification code, then close this panel and press Resume.
        </div>
      </div>
    </div>
  );
};
