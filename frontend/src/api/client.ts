import { DocumentItem, EvalReport, HealthResponse, IngestionStatus } from '../types/api';

export const API_BASE_URL: string = (import.meta as any).env?.VITE_API_URL || '';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export const checkHealth = () => getJson<HealthResponse>('/api/v1/health');
export const getDocuments = () => getJson<DocumentItem[]>('/api/v1/documents');
export const getIngestionStatus = () => getJson<IngestionStatus>('/api/v1/ingestion/status');
export const getEvalReport = () => getJson<EvalReport>('/api/v1/evaluation/report');

export const PAGE_IMAGE_DPI = 110;

export function pageImageUrl(docId: string, page: number, dpi = PAGE_IMAGE_DPI): string {
  return `${API_BASE_URL}/api/v1/documents/${encodeURIComponent(docId)}/page/${page}/image?dpi=${dpi}`;
}
