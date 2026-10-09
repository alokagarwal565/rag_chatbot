import { Timings } from '../types/api';

const fmt = (ms?: number | null) =>
  ms == null ? '—' : ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(2)}s`;

const SEGMENTS: [keyof Timings, string][] = [
  ['rewrite_ms', 'rewrite'],
  ['embed_ms', 'embed'],
  ['dense_ms', 'dense'],
  ['lexical_ms', 'bm25'],
  ['rerank_ms', 'rerank'],
  ['ttft_ms', 'LLM first token'],
  ['llm_ms', 'LLM total'],
];

export const LatencyBar = ({ timings }: { timings: Timings }) => (
  <div className="latency" title="Per-stage latency measured on the server">
    <span className={`lat-seg total ${(timings.e2e_ms ?? 0) > 5000 ? 'slow' : ''}`}>
      ⏱ end-to-end {fmt(timings.e2e_ms)}
    </span>
    {SEGMENTS.filter(([k]) => timings[k] != null && (k !== 'rewrite_ms' || (timings[k] as number) > 0)).map(([k, label]) => (
      <span key={k} className="lat-seg">{label} {fmt(timings[k] as number)}</span>
    ))}
  </div>
);
