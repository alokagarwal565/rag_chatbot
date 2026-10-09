import { useEffect, useState } from 'react';
import { getEvalReport } from '../api/client';
import { EvalReport } from '../types/api';

const pct = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);
const ms = (v?: number | null) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`);
const num = (v?: number | null, d = 3) => (v == null ? '—' : v.toFixed(d));

const Stat = ({ label, value, hint }: { label: string; value: string; hint?: string }) => (
  <div className="glass-card stat">
    <div className="label">{label}</div>
    <div className="value">{value}</div>
    {hint && <div className="hint">{hint}</div>}
  </div>
);

export const MetricsTab = () => {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalReport().then(setReport).catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div className="empty">No evaluation report yet. Run <code>python -m evaluation.runner</code>. ({error})</div>;
  }
  if (!report) return <div className="empty">Loading…</div>;

  const r = report.retrieval || {};
  const g = report.generation || {};
  const l = report.latency || {};
  const stages: string[] = Object.keys(l.stage_p50 || {});

  return (
    <div className="animate-fade-in" style={{ paddingBottom: '2rem' }}>
      <div className="section">
        <h2>Evaluation report</h2>
        <div className="sub">
          {report.n_questions} questions ({report.n_answerable} answerable, {report.n_unanswerable} unanswerable) ·
          generated {report.generated_at} · {report.hardware}
        </div>
      </div>

      <div className="section">
        <div className="panel-title">Retrieval</div>
        <div className="stat-grid">
          <Stat label="Recall@1" value={pct(r.recall_at_1)} />
          <Stat label="Recall@5" value={pct(r.recall_at_5)} />
          <Stat label="Recall@10" value={pct(r.recall_at_10)} />
          <Stat label="MRR@10" value={num(r.mrr_at_10)} />
        </div>
      </div>

      <div className="section">
        <div className="panel-title">Generation</div>
        <div className="stat-grid">
          <Stat label="Citation accuracy" value={pct(g.citation_accuracy)} hint="cited page = gold, or judge-supported" />
          <Stat label="Hallucination rate" value={pct(g.hallucination_rate)} hint="answers with ≥1 unsupported claim" />
          <Stat label="Unsupported claims" value={pct(g.unsupported_claim_rate)} hint="share of all judged claims" />
          <Stat label="Correct abstention" value={pct(g.correct_abstention_rate)} hint="on unanswerable questions" />
          <Stat label="False abstention" value={pct(g.false_abstention_rate)} hint="on answerable questions" />
        </div>
      </div>

      <div className="section">
        <div className="panel-title">Latency (client-measured, sequential)</div>
        <div className="stat-grid">
          <Stat label="End-to-end p50" value={ms(l.e2e_p50)} />
          <Stat label="End-to-end p95" value={ms(l.e2e_p95)} hint={l.e2e_p95 > 5000 ? 'over the 5 s target' : 'within the 5 s target'} />
          <Stat label="First token p50" value={ms(l.ttft_p50)} />
          <Stat label="First token p95" value={ms(l.ttft_p95)} />
        </div>
        {stages.length > 0 && (
          <div className="glass-panel panel table-wrap">
            <table className="data">
              <thead><tr><th>Stage</th><th>p50</th><th>p95</th></tr></thead>
              <tbody>
                {stages.map((s) => (
                  <tr key={s}><td>{s}</td><td className="num">{ms(l.stage_p50[s])}</td><td className="num">{ms(l.stage_p95[s])}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {Array.isArray(report.per_question) && (
        <div className="glass-panel panel">
          <div className="panel-title">Per-question results</div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>ID</th><th>Question</th><th>Gold</th><th>Hit rank</th><th>Abstained</th><th>Cit. acc.</th><th>Unsupported</th><th>E2E</th></tr>
              </thead>
              <tbody>
                {report.per_question.map((q: any) => (
                  <tr key={q.id}>
                    <td className="mono">{q.id}</td>
                    <td className="snippet">{q.question}</td>
                    <td>{q.answerable ? `${q.gold_filename} · p.${q.gold_page}` : <span className="badge dim">unanswerable</span>}</td>
                    <td className="num">{q.answerable ? (q.hit_rank ?? '—') : ''}</td>
                    <td>{q.abstained ? <span className={`badge ${q.answerable ? 'err' : 'ok'}`}>yes</span> : <span className={`badge ${q.answerable ? 'ok' : 'err'}`}>no</span>}</td>
                    <td className="num">{q.citation_accuracy == null ? '—' : pct(q.citation_accuracy)}</td>
                    <td className="num">{q.unsupported_claims ?? '—'}</td>
                    <td className="num">{ms(q.e2e_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
