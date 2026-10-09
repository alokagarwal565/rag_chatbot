import { useCallback } from 'react';
import { API_BASE_URL } from '../api/client';
import { HistoryTurn } from '../types/api';

export type StreamHandler = (event: string, data: any) => void;

/** POSTs to the SSE query endpoint and dispatches each `event:`/`data:` frame to `onEvent`. */
export function useStreamingQuery() {
  const streamQuery = useCallback(async (
    question: string,
    history: HistoryTurn[],
    onEvent: StreamHandler,
    signal: AbortSignal,
  ) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, conversation_history: history }),
        signal,
      });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.message || `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let sawDone = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          let type = 'message';
          const dataLines: string[] = [];
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) type = line.slice(6).trim();
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
          }
          if (!dataLines.length) continue;
          try {
            onEvent(type, JSON.parse(dataLines.join('\n')));
          } catch (e) {
            console.error('Bad SSE frame', e, frame);
          }
          if (type === 'done') sawDone = true;
        }
      }
      if (!sawDone) onEvent('done', {});
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      onEvent('error', { message: err?.message || 'Network error' });
      onEvent('done', {});
    }
  }, []);

  return { streamQuery };
}
