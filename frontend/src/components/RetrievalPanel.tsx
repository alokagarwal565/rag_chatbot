import { RetrievedChunk } from '../types/api';
import { CitationTarget, chunkTarget } from './AnswerPanel';

interface Props {
  chunks: RetrievedChunk[];
  pending: boolean;
  onOpen: (t: CitationTarget) => void;
}

const f = (v: number | null | undefined, d = 3) => (v == null ? '—' : v.toFixed(d));

export const RetrievalPanel = ({ chunks, pending, onOpen }: Props) => {
  if (!chunks.length) {
    return (
      <div className="glass-panel panel">
        <div className="panel-title">Retrieval</div>
        <div className="empty">{pending ? 'Retrieving…' : 'No passages retrieved.'}</div>
      </div>
    );
  }
  const maxRrf = Math.max(...chunks.map((c) => c.rrf_score), 1e-9);
  return (
    <div className="glass-panel panel animate-fade-in">
      <div className="panel-title">
        <span>Top {chunks.length} retrieved chunks</span>
        <span style={{ textTransform: 'none', fontWeight: 500 }}>dense + BM25 → RRF → rerank</span>
      </div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>#</th><th>File · page</th>
              <th title="Cosine similarity (rank)">Dense</th>
              <th title="FTS5 BM25 score (rank)">BM25</th>
              <th title="Reciprocal rank fusion, k=60">RRF</th>
              <th title="Cross-encoder relevance probability">Rerank</th>
              <th>Snippet</th>
            </tr>
          </thead>
          <tbody>
            {chunks.map((c) => (
              <tr key={c.chunk_id} className={`clickable ${c.cited ? 'cited' : c.in_context ? 'ctx' : ''}`}
                  onClick={() => onOpen(chunkTarget(c, c.context_n ? `[${c.context_n}]` : `#${c.rank}`))}>
                <td className="num">
                  {c.rank}
                  <div style={{ marginTop: 3 }}>
                    {c.cited ? <span className="badge cited">cited</span> : c.in_context ? <span className="badge ctx">ctx</span> : null}
                  </div>
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 600 }}>{c.filename}</div>
                  <div style={{ color: 'var(--text-dim)' }}>{c.page_label}{c.context_n ? ` · source [${c.context_n}]` : ''}</div>
                </td>
                <td className="num">{f(c.dense_score)}<div style={{ color: 'var(--text-dim)' }}>{c.dense_rank ? `#${c.dense_rank}` : '—'}</div></td>
                <td className="num">{f(c.bm25_score, 2)}<div style={{ color: 'var(--text-dim)' }}>{c.bm25_rank ? `#${c.bm25_rank}` : '—'}</div></td>
                <td className="num">
                  {f(c.rrf_score, 4)}
                  <div className="bar" style={{ marginTop: 4 }}><span style={{ width: `${(c.rrf_score / maxRrf) * 100}%` }} /></div>
                </td>
                <td className="num">
                  {c.rerank_prob == null ? '—' : f(c.rerank_prob)}
                  {c.rerank_prob != null && (
                    <div className="bar" style={{ marginTop: 4 }}><span style={{ width: `${c.rerank_prob * 100}%` }} /></div>
                  )}
                </td>
                <td className="snippet">{c.snippet}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="legend">
        <span><span className="badge cited">cited</span> used in the answer</span>
        <span><span className="badge ctx">ctx</span> sent to the LLM, not cited</span>
        <span>Click a row to open the page.</span>
      </div>
    </div>
  );
};
