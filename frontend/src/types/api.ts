export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'ABSTAIN';

/** page number (string key) -> [x0, y0, x1, y1] in PDF points */
export type BBoxMap = Record<string, number[]>;

export interface RetrievedChunk {
  rank: number;
  chunk_id: string;
  doc_id: string;
  filename: string;
  title: string;
  page_start: number;
  page_end: number;
  page_label: string;
  snippet: string;
  text: string;
  bboxes: BBoxMap;
  dense_rank: number | null;
  dense_score: number | null;
  bm25_rank: number | null;
  bm25_score: number | null;
  rrf_score: number;
  rerank_score: number | null;
  rerank_prob: number | null;
  in_context: boolean;
  context_n: number | null;
  cited: boolean;
}

export interface Citation {
  n: number;
  chunk_id: string;
  doc_id: string;
  filename: string;
  title: string;
  page_start: number;
  page_end: number;
  page_label: string;
  excerpt: string;
  bboxes: BBoxMap;
}

export interface Timings {
  rewrite_ms?: number;
  embed_ms?: number;
  dense_ms?: number;
  lexical_ms?: number;
  fusion_ms?: number;
  rerank_ms?: number;
  retrieval_ms?: number;
  ttft_ms?: number | null;
  llm_ms?: number | null;
  e2e_ms?: number;
}

export interface FinalPayload {
  answer: string;
  citations: Citation[];
  chunks: RetrievedChunk[];
  confidence: ConfidenceLevel;
  abstained: boolean;
  abstain_reason?: string | null;
  evidence_score: number;
  evidence_signal: string;
  invalid_citations_stripped: number;
  rewritten_query: string;
  model?: string | null;
  timings: Timings;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  kind?: 'answer' | 'fast' | 'decline' | 'error';
  streaming?: boolean;
  status?: string | null;
  chunks?: RetrievedChunk[];
  final?: FinalPayload;
  rewrittenQuery?: string;
}

export interface HistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface DocumentItem {
  doc_id: string;
  filename: string;
  title: string;
  page_count: number;
  native_pages: number;
  ocr_pages: number;
  chunk_count: number;
  language: string | null;
  status: string;
  stage: string | null;
  stage_timings: Record<string, number>;
  source_url?: string | null;
  license?: string | null;
  ingested_at?: string | null;
}

export interface IngestionStatus {
  documents: DocumentItem[];
  totals: {
    documents: number;
    pages: number;
    native_pages: number;
    ocr_pages: number;
    chunks: number;
    vectors: number;
  };
  running: boolean;
  last_run: { started_at: string; finished_at: string | null; status: string; stage_timings: Record<string, number> } | null;
  config: Record<string, string | number | boolean>;
}

export interface HealthResponse {
  status: string;
  service: string;
  documents: number;
  chunks: number;
  vectors: number;
  models_warm: boolean;
  reranker_enabled: boolean;
  llm_configured: boolean;
}

export type EvalReport = Record<string, any>;
