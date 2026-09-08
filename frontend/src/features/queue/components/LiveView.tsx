import { useEffect, useRef, useState } from 'react';
import { X, Play, XCircle } from 'lucide-react';
import { wsUrl } from '@/lib/wsUrl';
import { useResumeJobMutation, useCancelJobMutation } from '../services/queue.queries';

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
  const resumeMutation = useResumeJobMutation();
  const cancelMutation = useCancelJobMutation();

  // Real bug this fixes: this panel told the user to "press Resume" after
  // entering their code, but no enabled Resume control existed anywhere
  // while the application's status was needs_input (2FA) —
  // QueueControls' queue-wide Resume button is deliberately DISABLED for
  // that exact status (it points back here instead), and QueueTable's
  // per-row Resume only fires for rawStatus === 'paused', never
  // needs_input. The instruction referred to a button that didn't exist.
  // The backend also auto-resumes on its own once the challenge clears
  // (polled every few seconds — see runner.py's _handle_2fa_if_present),
  // so this button is a faster, explicit alternative to that polling,
  // not the only way forward if the user forgets to click it.
  const handleResume = () => {
    resumeMutation.mutate(applicationId, { onSuccess: onClose });
  };

  // Per user direction: rather than send the user hunting for a
  // queue-level Cancel control (which had its own gating bugs — see
  // FLAGGED.md #30), give the choice right here, at the exact moment
  // they're asked to act on this job — resume it, or give up on it.
  const handleCancel = () => {
    cancelMutation.mutate(applicationId, { onSuccess: onClose });
  };

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

        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 shrink-0 flex items-center justify-between gap-3">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Click into the browser above and enter your verification code, then press Resume — or
            Cancel to give up on this application. The agent will also continue automatically if
            the challenge clears on its own.
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleCancel}
              disabled={cancelMutation.isPending || resumeMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 border border-red-200 dark:border-red-900/40 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors rounded-lg text-sm font-semibold disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" /> Cancel
            </button>
            <button
              onClick={handleResume}
              disabled={resumeMutation.isPending || cancelMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white transition-colors rounded-lg text-sm font-semibold disabled:opacity-50"
            >
              <Play className="w-4 h-4" /> Resume
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
