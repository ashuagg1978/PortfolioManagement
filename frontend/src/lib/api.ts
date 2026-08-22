// A small typed fetch wrapper - no axios. All requests go through /api,
// proxied to the backend in dev by vite.config.ts and served from the same
// origin in a production build.

import type {
  Account,
  CommissionPreview,
  CommitResult,
  DashboardSummary,
  DueEntry,
  ImportBatch,
  ImportRow,
  SchemeHolding,
  SchemeSearchResult,
  Sip,
  SyncResponse,
  Transaction,
  TransactionType,
  UpcomingOccurrence,
} from '../types/api';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON - keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function get<T>(path: string): Promise<T> {
  return request<T>(path);
}
function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}
function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
}
function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' });
}

// --- accounts ---
export const listAccounts = () => get<Account[]>('/accounts');

// --- NAV / schemes ---
export const syncNav = () => post<SyncResponse>('/nav/sync');
export const searchSchemes = (q: string, limit = 20) =>
  q.trim().length < 2
    ? Promise.resolve([])
    : get<SchemeSearchResult[]>(`/schemes/search?q=${encodeURIComponent(q)}&limit=${limit}`);

// --- transactions ---
export interface TransactionFilters {
  account_id?: number;
  scheme_code?: string;
  type?: TransactionType;
  date_from?: string;
  date_to?: string;
  include_deleted?: boolean;
}
export const listTransactions = (filters: TransactionFilters = {}) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return get<Transaction[]>(`/transactions${qs ? `?${qs}` : ''}`);
};
export interface TransactionInput {
  account_id: number;
  scheme_code: string;
  transaction_date: string;
  type: TransactionType;
  nav: number;
  units: number;
  amount: number;
  folio_no?: string | null;
}
export const createTransaction = (input: TransactionInput) => post<Transaction>('/transactions', input);
export const updateTransaction = (
  id: number,
  input: Pick<TransactionInput, 'transaction_date' | 'nav' | 'units' | 'amount' | 'folio_no'>,
) => patch<Transaction>(`/transactions/${id}`, input);
export const softDeleteTransaction = (id: number) => del<Transaction>(`/transactions/${id}`);
export const restoreTransaction = (id: number) => post<Transaction>(`/transactions/${id}/restore`);
export const previewCommission = (input: {
  type: TransactionType;
  nav: number;
  units: number;
  amount: number;
}) => post<CommissionPreview>('/transactions/preview-commission', input);

// --- dashboard ---
export const getDashboard = () => get<DashboardSummary>('/dashboard');
export const getHoldings = () => get<SchemeHolding[]>('/dashboard/holdings');

// --- SIPs ---
export interface SipInput {
  account_id: number;
  scheme_code: string;
  amount: number;
  frequency: 'MONTHLY' | 'BIWEEKLY';
  start_date: string;
  end_date?: string | null;
  folio_no?: string | null;
}
export const listSips = (activeOnly = true) => get<Sip[]>(`/sips?active_only=${activeOnly}`);
export const createSip = (input: SipInput) => post<Sip>('/sips', input);
export const versionSip = (
  id: number,
  input: { effective_date: string; amount?: number; frequency?: string; folio_no?: string | null },
) => post<Sip>(`/sips/${id}/version`, input);
export const getDueEntries = () => get<DueEntry[]>('/sips/due');
export const getDueCount = () => get<{ count: number }>('/sips/due/count');
export const confirmDueEntry = (input: { sip_id: number; scheduled_date: string; nav: number; units: number }) =>
  post<Transaction>('/sips/due/confirm', input);
export const skipDueEntry = (input: { sip_id: number; scheduled_date: string; reason?: string }) =>
  post<{ id: number }>('/sips/due/skip', input);
export const getUpcoming = (n = 5) => get<UpcomingOccurrence[]>(`/sips/upcoming?n=${n}`);

// --- imports ---
export const uploadImport = async (file: File, accountId: number): Promise<ImportBatch> => {
  const form = new FormData();
  form.append('file', file);
  form.append('account_id', String(accountId));
  const res = await fetch('/api/imports', { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
};
export const getImportBatch = (id: number) => get<ImportBatch>(`/imports/${id}`);
export const getImportRows = (id: number, action?: string) =>
  get<ImportRow[]>(`/imports/${id}/rows${action ? `?action=${action}` : ''}`);
export const mapImportScheme = (id: number, key: string, scheme_code: string) =>
  post<ImportBatch>(`/imports/${id}/mappings/scheme`, { key, scheme_code });
export const commitImportBatch = (id: number) => post<CommitResult>(`/imports/${id}/commit`);
