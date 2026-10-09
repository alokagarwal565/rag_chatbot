import { useCallback, useEffect, useRef, useState } from 'react';
import { checkHealth } from './api/client';
import { AnswerPanel, CitationTarget } from './components/AnswerPanel';
import { IngestionTab } from './components/IngestionTab';
import { MetricsTab } from './components/MetricsTab';
import { PageImageModal } from './components/PageImageModal';
import { QueryInput } from './components/QueryInput';
import { RetrievalPanel } from './components/RetrievalPanel';
import { useStreamingQuery } from './hooks/useStreamingQuery';
import { HealthResponse, HistoryTurn, Message } from './types/api';

type Tab = 'chat' | 'ingestion' | 'metrics';

const STARTERS = [
  { tag: 'Biology', text: 'What happens during the light-dependent reactions of photosynthesis?' },
  { tag: 'Physics', text: "How is Newton's second law expressed in terms of momentum?" },
  { tag: 'Economics', text: 'What causes a shift in the demand curve, as opposed to a movement along it?' },
  { tag: 'Psychology', text: 'What is the difference between classical and operant conditioning?' },
];

const stripCitations = (s: string) => s.replace(/\[\d{1,2}\]/g, '').trim();

export default function App() {
  const [tab, setTab] = useState<Tab>('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [modal, setModal] = useState<CitationTarget | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { streamQuery } = useStreamingQuery();

  useEffect(() => {
    const load = () => checkHealth().then((h) => { setHealth(h); setHealthError(false); }).catch(() => setHealthError(true));
    load();
    const id = setInterval(load, 15000);
    return () => { clearInterval(id); abortRef.current?.abort(); };
  }, []);

  useEffect(() => {
    if (tab === 'chat') bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, tab]);

  const update = (id: string, fn: (m: Message) => Message) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));

  const handleSearch = useCallback((question: string) => {
    if (!question.trim() || isStreaming) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    const history: HistoryTurn[] = messages
      .filter((m) => !m.streaming && (m.role === 'user' || m.kind === 'answer') && !m.final?.abstained)
      .map((m) => ({ role: m.role, content: stripCitations(m.final?.answer ?? m.content) }))
      .filter((t) => t.content)
      .slice(-6);

    const uid = `u-${Date.now()}`;
    const aid = `a-${Date.now()}`;
    setMessages((prev) => [...prev,
      { id: uid, role: 'user', content: question },
      { id: aid, role: 'assistant', content: '', kind: 'answer', streaming: true, status: 'Connecting…' }]);
    setIsStreaming(true);

    streamQuery(question, history, (type, data) => {
      switch (type) {
        case 'status': update(aid, (m) => ({ ...m, status: data.message })); break;
        case 'rewrite': update(aid, (m) => ({ ...m, rewrittenQuery: data.rewritten })); break;
        case 'retrieval': update(aid, (m) => ({ ...m, chunks: data.chunks })); break;
        case 'token': update(aid, (m) => ({ ...m, content: m.content + data.text })); break;
        case 'final': update(aid, (m) => ({ ...m, final: data, chunks: data.chunks, status: null })); break;
        case 'fast_path': update(aid, (m) => ({ ...m, kind: 'fast', content: data.message })); break;
        case 'decline': update(aid, (m) => ({ ...m, kind: 'decline', content: data.message })); break;
        case 'error': update(aid, (m) => (m.final ? m : { ...m, kind: 'error', content: data.message })); break;
        case 'done':
          update(aid, (m) => ({ ...m, streaming: false, status: null }));
          setIsStreaming(false);
          abortRef.current = null;
          break;
      }
    }, abortRef.current.signal);
  }, [isStreaming, messages, streamQuery]);

  const stop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) => prev.map((m) => (m.streaming ? { ...m, streaming: false, status: null } : m)));
  };

  const healthy = !!health && !healthError;

  return (
    <div className="app-shell">
      <header className="glass-panel app-header">
        <div className="brand">
          <div className="brand-logo">ग</div>
          <div>
            <h1>Granth</h1>
            <small>Open-Source PDF Knowledge Assistant</small>
          </div>
        </div>
        <nav className="tabs">
          {(['chat', 'ingestion', 'metrics'] as Tab[]).map((t) => (
            <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
              {t === 'chat' ? 'Chat' : t === 'ingestion' ? 'Ingestion' : 'Metrics'}
            </button>
          ))}
        </nav>
        <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
          {tab === 'chat' && messages.length > 0 && (
            <button className="btn" onClick={() => { stop(); setMessages([]); }}>New chat</button>
          )}
          <span className="status-pill" title={health ? `reranker ${health.reranker_enabled ? 'on' : 'off'} · LLM ${health.llm_configured ? 'configured' : 'missing key'}` : ''}>
            <span className="dot" style={{ background: healthy ? (health!.models_warm ? 'var(--accent-emerald)' : 'var(--accent)') : 'var(--accent-rose)' }} />
            {healthy
              ? `${health!.documents} PDFs · ${health!.chunks.toLocaleString()} chunks${health!.models_warm ? '' : ' · warming'}`
              : 'API offline'}
          </span>
        </div>
      </header>

      {tab === 'ingestion' && <IngestionTab />}
      {tab === 'metrics' && <MetricsTab />}

      {tab === 'chat' && (
        <main className="chat-main">
          {messages.length === 0 && (
            <div className="animate-fade-in">
              <div className="hero">
                <h2>Ask questions across your PDF library</h2>
                <p>
                  Hybrid retrieval (dense HNSW + BM25 → RRF → cross-encoder rerank) over native and OCR'd pages.
                  Every answer cites the file and page, and you can open the page to see the exact passage.
                </p>
              </div>
              <div className="starter-grid">
                {STARTERS.map((s) => (
                  <div key={s.text} className="glass-card clickable starter" onClick={() => handleSearch(s.text)}>
                    <div className="tag">{s.tag}</div>
                    <p>{s.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => {
            if (m.role === 'user') {
              return <div key={m.id} className="user-row"><div className="user-bubble">{m.content}</div></div>;
            }
            const rag = m.kind === 'answer';
            const user = messages[i - 1];
            return (
              <div key={m.id} className={rag ? 'answer-layout' : ''} style={rag ? undefined : { marginBottom: '1.5rem' }}>
                <AnswerPanel message={m} onOpen={setModal} />
                {rag && (
                  <RetrievalPanel chunks={m.chunks || []} pending={!!m.streaming} onOpen={setModal} key={`r-${user?.id}`} />
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </main>
      )}

      {tab === 'chat' && (
        <div className="dock">
          <div className="dock-inner">
            <QueryInput onSearch={handleSearch} isLoading={isStreaming} onStop={stop} />
          </div>
        </div>
      )}

      {modal && <PageImageModal target={modal} onClose={() => setModal(null)} />}
    </div>
  );
}
