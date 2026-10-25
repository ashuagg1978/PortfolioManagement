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
  NavHistoryPoint,
  PortfolioAdvice,
  PortfolioHistoryPoint,
  SchemeAdvice,
  SchemeHolding,
  SchemeSearchResult,
  Sip,
  SyncResponse,
  Transaction,
  TransactionListResponse,
  TransactionSource,
  TransactionType,
  UpcomingOccurrence,
} from '../types/api';

/** Backend origin for production builds (e.g. http://host:8000); empty in dev,
 * where Vite's proxy forwards the relative /api paths. */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, {
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
export interface AccountInput {
  account_name: string;
  platform: string;
}
export const listAccounts = () => get<Account[]>('/accounts');
export const createAccount = (input: AccountInput) => post<Account>('/accounts', input);
export const updateAccount = (id: number, input: AccountInput) => patch<Account>(`/accounts/${id}`, input);

// --- NAV / schemes ---
export const syncNav = () => post<SyncResponse>('/nav/sync');
export const searchSchemes = (q: string, limit = 20) =>
  q.trim().length < 2
    ? Promise.resolve([])
    : get<SchemeSearchResult[]>(`/schemes/search?q=${encodeURIComponent(q)}&limit=${limit}`);
/** NAV on (or the closest trading day before) the given date, sourced from
 * mfapi.in's historical data - a prefill convenience, not authoritative.
 * Returns null (not an error) when nothing is found. */
export const getNavOnDate = (schemeCode: string, on: string) =>
  get<NavHistoryPoint | null>(`/schemes/${schemeCode}/nav-history?on=${on}`);

// --- transactions ---
export interface TransactionFilters {
  account_id?: number;
  scheme_code?: string;
  scheme_name?: string;
  type?: TransactionType;
  source?: TransactionSource;
  date_from?: string;
  date_to?: string;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
}
function buildQuery(filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters as Record<string, unknown>)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  return params.toString();
}
export const listTransactions = (filters: TransactionFilters = {}) => {
  const qs = buildQuery(filters);
  return get<TransactionListResponse>(`/transactions${qs ? `?${qs}` : ''}`);
};
/** A plain download URL (not a fetch call) - the caller renders this as an
 * <a href> so the browser handles the file save, same pattern as the
 * import template download. Excludes limit/offset - export always covers
 * the full filtered set, not just the current page. */
export const transactionsExportUrl = (filters: Omit<TransactionFilters, 'limit' | 'offset'> = {}) => {
  const qs = buildQuery(filters);
  return `${API_BASE}/api/transactions/export${qs ? `?${qs}` : ''}`;
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
  allow_duplicate?: boolean;
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
export const getSavedPortfolioAdvice = () => get<PortfolioAdvice | null>('/advisor/portfolio');
export const getSavedSchemeAdvice = (schemeCode: string) =>
  get<SchemeAdvice | null>(`/advisor/schemes/${encodeURIComponent(schemeCode)}`);
export const getPortfolioAdvice = () => post<PortfolioAdvice>('/advisor/portfolio');
export const getSchemeAdvice = (schemeCode: string) =>
  post<SchemeAdvice>(`/advisor/schemes/${encodeURIComponent(schemeCode)}`);
export const getPortfolioHistory = () => get<PortfolioHistoryPoint[]>('/dashboard/history');

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
export const holdSip = (id: number) => post<Sip>(`/sips/${id}/hold`);
export const resumeSip = (id: number) => post<Sip>(`/sips/${id}/resume`);
export const stopSip = (id: number, end_date?: string) => post<Sip>(`/sips/${id}/stop`, { end_date });
export const getDueEntries = () => get<DueEntry[]>('/sips/due');
export const getDueCount = () => get<{ count: number }>('/sips/due/count');
export const confirmDueEntry = (input: {
  sip_id: number;
  scheduled_date: string;
  transaction_date?: string; // overrides the system-computed trading-day-adjusted date
  nav: number;
  units: number;
}) => post<Transaction>('/sips/due/confirm', input);
export const skipDueEntry = (input: { sip_id: number; scheduled_date: string; reason?: string }) =>
  post<{ id: number }>('/sips/due/skip', input);
export const getUpcoming = (n = 5) => get<UpcomingOccurrence[]>(`/sips/upcoming?n=${n}`);

// --- imports ---
export const uploadImport = async (file: File, accountId: number): Promise<ImportBatch> => {
  const form = new FormData();
  form.append('file', file);
  form.append('account_id', String(accountId));
  const res = await fetch(`${API_BASE}/api/imports`, { method: 'POST', body: form });
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
