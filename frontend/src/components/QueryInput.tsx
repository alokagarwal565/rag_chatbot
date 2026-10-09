import { useEffect, useRef, useState } from 'react';

interface Props {
  onSearch: (question: string) => void;
  isLoading: boolean;
  onStop?: () => void;
}

export const QueryInput = ({ onSearch, isLoading, onStop }: Props) => {
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [query]);

  const submit = () => {
    if (!query.trim() || isLoading) return;
    onSearch(query.trim());
    setQuery('');
  };

  return (
    <>
      <div className="glass-panel query-box">
        <textarea
          ref={ref}
          rows={1}
          value={query}
          placeholder="Ask a question about the indexed PDFs…"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
          }}
        />
        {isLoading && onStop ? (
          <button className="btn" onClick={onStop}>Stop</button>
        ) : (
          <button className="btn btn-primary" disabled={!query.trim() || isLoading} onClick={submit}>Ask</button>
        )}
      </div>
      <div className="dock-hint">Answers come only from the indexed documents and cite file + page. Enter to send · Shift+Enter for a new line.</div>
    </>
  );
};
