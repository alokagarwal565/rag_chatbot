import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Citation, Message, RetrievedChunk } from '../types/api';
import { ConfidenceBadge } from './ConfidenceBadge';
import { LatencyBar } from './LatencyBar';

export interface CitationTarget {
  label: string;
  doc_id: string;
  filename: string;
  title: string;
  page_start: number;
  page_end: number;
  bboxes: Record<string, number[]>;
  text: string;
}

interface Props {
  message: Message;
  onOpen: (target: CitationTarget) => void;
}

const CITE_RE = /\[(\d{1,2})\](?!\()/g;

export function chunkTarget(c: RetrievedChunk, label: string): CitationTarget {
  return { label, doc_id: c.doc_id, filename: c.filename, title: c.title, page_start: c.page_start,
           page_end: c.page_end, bboxes: c.bboxes, text: c.text };
}

function citationTarget(c: Citation, ctx?: RetrievedChunk): CitationTarget {
  return { label: `[${c.n}]`, doc_id: c.doc_id, filename: c.filename, title: c.title, page_start: c.page_start,
           page_end: c.page_end, bboxes: c.bboxes, text: ctx?.text || c.excerpt };
}

export const AnswerPanel = ({ message, onOpen }: Props) => {
  const final = message.final;
  const chunks = final?.chunks || message.chunks || [];
  const contextByN = new Map<number, RetrievedChunk>();
  chunks.forEach((c) => { if (c.context_n) contextByN.set(c.context_n, c); });

  if (message.kind === 'fast') return <div className="notice fast animate-fade-in">{message.content}</div>;
  if (message.kind === 'decline') return <div className="notice decline animate-fade-in">{message.content}</div>;
  if (message.kind === 'error') return <div className="notice error animate-fade-in">⚠ {message.content}</div>;

  const body = final ? final.answer : message.content;
  const md = body.replace(CITE_RE, (_m, n) => `[${n}](#cite-${n})`);
  const abstained = final?.abstained;

  const openN = (n: number) => {
    const cit = final?.citations.find((c) => c.n === n);
    const ctx = contextByN.get(n);
    if (cit) onOpen(citationTarget(cit, ctx));
    else if (ctx) onOpen(chunkTarget(ctx, `[${n}]`));
  };

  return (
    <div className="glass-panel answer-card animate-fade-in">
      <div className="answer-head">
        <span className="answer-title">Answer</span>
        {final && <ConfidenceBadge confidence={final.confidence} />}
      </div>

      {final && final.rewritten_query && final.rewritten_query !== '' && (
        <div className="rewrite-note">Searched for: “{final.rewritten_query}”</div>
      )}

      {message.streaming && !body && (
        <div className="stage-line"><span className="spinner" /> {message.status || 'Working…'}</div>
      )}

      {abstained ? (
        <div className="notice abstain">
          <strong>I couldn't find this in the indexed documents.</strong>
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            {final?.abstain_reason || 'The retrieved passages do not support an answer, so none was generated.'}
            {' '}The closest passages are listed in the retrieval panel.
          </div>
        </div>
      ) : (
        body && (
          <div className="markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  if (href?.startsWith('#cite-')) {
                    const n = Number(href.slice(6));
                    const c = contextByN.get(n);
                    return (
                      <button className="cite-chip" onClick={() => openN(n)}
                              title={c ? `${c.filename} · ${c.page_label}` : `source ${n}`}>{n}</button>
                    );
                  }
                  return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
                },
              }}
            >
              {md}
            </ReactMarkdown>
            {message.streaming && <span className="streaming-cursor" />}
          </div>
        )
      )}

      {message.streaming && body && message.status && (
        <div className="stage-line" style={{ marginTop: '0.5rem' }}><span className="spinner" /> {message.status}</div>
      )}

      {final && !abstained && final.citations.length > 0 && (
        <div className="sources">
          <h4>Sources ({final.citations.length})
            {final.invalid_citations_stripped > 0 && (
              <span className="badge warn" style={{ marginLeft: 8 }}>
                {final.invalid_citations_stripped} invalid citation{final.invalid_citations_stripped > 1 ? 's' : ''} removed
              </span>
            )}
          </h4>
          <div className="source-list">
            {final.citations.map((c) => (
              <button key={c.n} className="source-chip" onClick={() => onOpen(citationTarget(c, contextByN.get(c.n)))}>
                <b>[{c.n}]</b> {c.filename} · {c.page_label}
              </button>
            ))}
          </div>
        </div>
      )}

      {final && <LatencyBar timings={final.timings} />}
    </div>
  );
};
