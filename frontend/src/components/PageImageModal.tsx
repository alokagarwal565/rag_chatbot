import { useEffect, useState } from 'react';
import { PAGE_IMAGE_DPI, pageImageUrl } from '../api/client';
import { CitationTarget } from './AnswerPanel';

interface Props {
  target: CitationTarget;
  onClose: () => void;
}

export const PageImageModal = ({ target, onClose }: Props) => {
  const [page, setPage] = useState(target.page_start);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => { setPage(target.page_start); }, [target]);
  useEffect(() => { setNatural(null); setFailed(false); }, [page, target.doc_id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const box = target.bboxes[String(page)];
  const scale = PAGE_IMAGE_DPI / 72;
  const pages = [];
  for (let p = target.page_start; p <= target.page_end; p++) pages.push(p);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="glass-panel modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-page">
          {failed ? (
            <div className="empty">Page image unavailable.</div>
          ) : (
            <div className="page-frame">
              <img
                src={pageImageUrl(target.doc_id, page)}
                alt={`${target.filename} page ${page}`}
                onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                onError={() => setFailed(true)}
              />
              {natural && box && (
                <div className="bbox" style={{
                  left: `${(box[0] * scale / natural.w) * 100}%`,
                  top: `${(box[1] * scale / natural.h) * 100}%`,
                  width: `${((box[2] - box[0]) * scale / natural.w) * 100}%`,
                  height: `${((box[3] - box[1]) * scale / natural.h) * 100}%`,
                }} />
              )}
            </div>
          )}
        </div>
        <div className="modal-side">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'flex-start' }}>
            <div>
              <span className="badge cited">{target.label}</span>
              <h3 style={{ marginTop: '0.4rem' }}>{target.filename} · p.{page}</h3>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{target.title}</div>
            </div>
            <button className="btn" onClick={onClose}>✕</button>
          </div>
          {pages.length > 1 && (
            <div className="page-nav">
              Chunk spans pages:
              {pages.map((p) => (
                <button key={p} className={`btn ${p === page ? 'btn-primary' : ''}`} onClick={() => setPage(p)}>{p}</button>
              ))}
            </div>
          )}
          <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '0.6rem' }}>
            Highlighted box = region of this page the chunk was taken from.
          </div>
          <div className="excerpt">{target.text}</div>
        </div>
      </div>
    </div>
  );
};
