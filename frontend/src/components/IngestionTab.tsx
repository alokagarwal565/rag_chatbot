import { useEffect, useState } from 'react';
import { getIngestionStatus } from '../api/client';
import { IngestionStatus } from '../types/api';
import { PipelineDiagram } from './PipelineDiagram';

const secs = (v?: number) => (v == null ? '—' : v >= 60 ? `${(v / 60).toFixed(1)}m` : `${v.toFixed(1)}s`);

const statusBadge = (s: string) => {
  const cls = s === 'done' ? 'ok' : s === 'failed' ? 'err' : s === 'pending' ? 'dim' : 'warn';
  return <span className={`badge ${cls}`}>{s}</span>;
};

export const IngestionTab = () => {
  const [status, setStatus] = useState<IngestionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => getIngestionStatus()
      .then((s) => { if (alive) { setStatus(s); setError(null); } })
      .catch((e) => alive && setError(String(e)));
    load();
    const id = setInterval(load, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const t = status?.totals;
  return (
    <div className="animate-fade-in" style={{ paddingBottom: '2rem' }}>
      <div className="section">
        <h2>Ingestion pipeline</h2>
        <div className="sub">
          PDF → extract / OCR → clean → chunk → embed → vector DB. Run with <code>python -m ingestion</code>;
          this page refreshes every 5 s{status?.running ? ' — a run is in progress' : ''}.
        </div>
        <PipelineDiagram status={status} />
      </div>

      {error && <div className="notice error">Could not load ingestion status: {error}</div>}

      {t && (
        <div className="stat-grid">
          <div className="glass-card stat"><div className="label">PDFs</div><div className="value">{t.documents}</div></div>
          <div className="glass-card stat"><div className="label">Pages</div><div className="value">{t.pages.toLocaleString()}</div></div>
          <div className="glass-card stat"><div className="label">Native pages</div><div className="value">{t.native_pages.toLocaleString()}</div></div>
          <div className="glass-card stat"><div className="label">OCR pages</div><div className="value">{t.ocr_pages.toLocaleString()}</div></div>
          <div className="glass-card stat"><div className="label">Chunks</div><div className="value">{t.chunks.toLocaleString()}</div></div>
          <div className="glass-card stat"><div className="label">Vectors (Chroma)</div><div className="value">{t.vectors.toLocaleString()}</div></div>
        </div>
      )}

      <div className="glass-panel panel">
        <div className="panel-title">Documents</div>
        {!status?.documents.length ? (
          <div className="empty">No documents yet. Run <code>python scripts/download_corpus.py</code> then <code>python -m ingestion</code>.</div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>File</th><th>Pages</th><th>Native</th><th>OCR</th><th>Chunks</th><th>Lang</th><th>Status</th>
                  <th>Extract</th><th>Clean</th><th>Chunk</th><th>Embed</th><th>Index</th><th>Total</th>
                </tr>
              </thead>
              <tbody>
                {status.documents.map((d) => {
                  const st = d.stage_timings || {};
                  const total = Object.values(st).reduce((a, b) => a + b, 0);
                  return (
                    <tr key={d.doc_id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{d.filename}</div>
                        <div style={{ color: 'var(--text-dim)' }}>{d.title}{d.license ? ` · ${d.license}` : ''}</div>
                      </td>
                      <td className="num">{d.page_count}</td>
                      <td className="num">{d.native_pages}</td>
                      <td className="num">{d.ocr_pages > 0 ? <span className="badge warn">{d.ocr_pages}</span> : 0}</td>
                      <td className="num">{d.chunk_count}</td>
                      <td>{d.language || '—'}</td>
                      <td>{statusBadge(d.status)}{d.stage && d.status !== 'done' ? <div style={{ color: 'var(--text-dim)' }}>{d.stage}</div> : null}</td>
                      <td className="num">{secs(st.extract)}</td>
                      <td className="num">{secs(st.clean)}</td>
                      <td className="num">{secs(st.chunk)}</td>
                      <td className="num">{secs(st.embed)}</td>
                      <td className="num">{secs(st.index)}</td>
                      <td className="num">{secs(total)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
