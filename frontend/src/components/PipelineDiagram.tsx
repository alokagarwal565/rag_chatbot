import { IngestionStatus } from '../types/api';

const secs = (v?: number) => (v == null ? '' : v >= 60 ? `${(v / 60).toFixed(1)} min` : `${v.toFixed(1)} s`);

export const PipelineDiagram = ({ status }: { status: IngestionStatus | null }) => {
  const t = status?.totals;
  const sum = (key: string) =>
    status?.documents.reduce((a, d) => a + (d.stage_timings?.[key] || 0), 0);
  const cfg = status?.config || {};
  const stages = [
    { name: 'PDF', what: 'Source files (sha256-tracked)', meta: t ? `${t.documents} files · ${t.pages.toLocaleString()} pages` : '' },
    { name: 'Extract / OCR', what: 'PyMuPDF native text; RapidOCR for scanned pages & large images',
      meta: t ? `${t.native_pages.toLocaleString()} native · ${t.ocr_pages.toLocaleString()} OCR · ${secs(sum('extract'))}` : '' },
    { name: 'Clean', what: 'Header/footer removal, page numbers, unicode, de-hyphenation, language',
      meta: secs(sum('clean')) },
    { name: 'Chunk', what: `${cfg.chunk_target_tokens ?? 480}-token windows, ${cfg.chunk_overlap_tokens ?? 72} overlap, page + bbox`,
      meta: t ? `${t.chunks.toLocaleString()} chunks · ${secs(sum('chunk'))}` : '' },
    { name: 'Embed', what: `${cfg.embedding_model ?? 'bge-small-en-v1.5'} (ONNX, CPU)`, meta: secs(sum('embed')) },
    { name: 'Index', what: 'Chroma HNSW (cosine) + SQLite FTS5 (BM25)',
      meta: t ? `${t.vectors.toLocaleString()} vectors · ${secs(sum('index'))}` : '' },
  ];
  return (
    <div className="glass-panel pipeline">
      {stages.map((s, i) => (
        <div key={s.name} style={{ display: 'contents' }}>
          <div className="pipe-stage">
            <div className="name">{s.name}</div>
            <div className="what">{s.what}</div>
            {s.meta && <div className="meta">{s.meta}</div>}
          </div>
          {i < stages.length - 1 && <div className="pipe-arrow">→</div>}
        </div>
      ))}
    </div>
  );
};
