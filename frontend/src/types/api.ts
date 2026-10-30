// Mirrors backend/app/schemas/*.py. Money/NAV/units fields arrive as plain
// JSON numbers (see backend/app/schemas/types.py's PlainSerializer) even
// though they're Decimal server-side.

export interface Account {
  id: number;
  account_name: string;
  platform: string;
}

export type TransactionType = 'PURCHASE' | 'REDEMPTION';
export type TransactionSource = 'MANUAL' | 'SIP' | 'IMPORT';

export interface Transaction {
  id: number;
  account_id: number;
  account_name: string;
  scheme_code: string;
  scheme_display_name: string;
  transaction_date: string; // YYYY-MM-DD
  type: TransactionType;
  source: TransactionSource;
  sip_id: number | null;
  amount: number;
  nav: number;
  units: number;
  commission: number;
  signed_amount: number;
  folio_no: string | null;
  is_deleted: boolean;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
}

export interface SchemeSearchResult {
  scheme_code: string;
  scheme_name: string;
  plan: string | null;
  option: string | null;
  latest_nav: number | null;
  nav_date: string | null;
}

export interface NavHistoryPoint {
  nav: number;
  nav_date: string;
}

export interface SyncResponse {
  rows_parsed: number;
  rows_upserted: number;
  rows_skipped: number;
  feed_date: string | null;
  duration_ms: number;
  history_schemes_synced: number;
  history_schemes_failed: number;
  history_points_inserted: number;
  history_duration_ms: number;
}

export interface PortfolioHistoryPoint {
  as_of: string; // YYYY-MM-DD
  current_value: number;
  net_invested: number;
  pct_gain: number | null;
}

export interface SchemeHolding {
  scheme_code: string;
  display_name: string;
  net_units: number;
  net_invested: number;
  avg_cost_nav: number | null;
  latest_nav: number | null;
  nav_date: string | null;
  nav_source: 'NAVAll' | 'Last txn NAV' | 'Redeemed';
  current_value: number;
  unrealized_gain: number;
  realized_gain: number;
  total_gain: number;
  pct_gain: number | null;
  status: 'In Profit' | 'In Loss' | 'Redeemed' | 'Flat';
  xirr: number | null;
}

export interface AdviceSource {
  title: string;
  url: string;
}

export interface SchemeAdvice {
  scheme_code: string;
  display_name: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  confidence: 'LOW' | 'MEDIUM' | 'HIGH';
  rationale: string;
  risks: string[];
  sources: AdviceSource[];
  model: string;
  disclaimer: string;
  generated_at: string | null;
}

export interface PortfolioAdviceAction {
  scheme_code: string | null;
  scheme_name: string;
  action: 'INCREASE' | 'REDUCE' | 'EXIT' | 'REPLACE' | 'HOLD';
  suggestion: string;
  rationale: string;
}

export interface PortfolioAdvice {
  summary: string;
  actions: PortfolioAdviceAction[];
  diversification_notes: string[];
  sources: AdviceSource[];
  model: string;
  disclaimer: string;
  generated_at: string | null;
}

export interface AccountHoldings {
  account_id: number;
  account_name: string;
  net_invested: number;
  current_value: number;
  net_gain_loss: number;
  pct_gain: number | null;
  xirr: number | null;
  schemes: SchemeHolding[];
}

export interface DashboardSummary {
  net_invested: number;
  current_value: number;
  net_gain_loss: number;
  total_realized_gain: number;
  total_return_pct: number | null;
  active_schemes: number;
  total_commission_paid: number;
  portfolio_xirr: number | null;
  nav_as_of: string | null;
  holdings: SchemeHolding[];
  by_account: AccountHoldings[];
}

export type SipFrequency = 'MONTHLY' | 'BIWEEKLY';

export interface Sip {
  id: number;
  account_id: number;
  account_name: string;
  scheme_code: string;
  scheme_display_name: string;
  amount: number;
  frequency: SipFrequency;
  start_date: string;
  end_date: string | null;
  folio_no: string | null;
  is_active: boolean;
  parent_sip_id: number | null;
}

export interface DueEntry {
  sip_id: number;
  account_id: number;
  account_name: string;
  scheme_code: string;
  display_name: string;
  scheduled_date: string;
  adjusted_date: string;
  expected_amount: number;
  folio_no: string | null;
  calendar_complete: boolean;
}

export interface UpcomingOccurrence {
  sip_id: number;
  account_name: string;
  scheme_code: string;
  display_name: string;
  scheduled_date: string;
  adjusted_date: string;
  amount: number;
}

export type ImportRowAction = 'NEW' | 'DUPLICATE' | 'UNMAPPED' | 'ERROR';

export interface ImportBatch {
  id: number;
  filename: string;
  status: 'PENDING' | 'COMMITTED';
  account_id: number | null;
  account_name: string | null;
  row_count: number;
  action_counts: Record<string, number>;
  unmapped_scheme_keys: string[];
  // Only present on the response from the upload call itself, not a later GET.
  sheet_used: string | null;
  other_sheets_ignored: string[];
}

export interface ImportRow {
  id: number;
  row_index: number;
  sheet_name: string | null;
  raw_scheme_name: string | null;
  scheme_code_hint: string | null;
  resolved_scheme_code: string | null;
  transaction_date: string | null;
  type: TransactionType | null;
  amount: number | null;
  nav: number | null;
  units: number | null;
  folio_no: string | null;
  action: ImportRowAction;
  error: string | null;
}

export interface CommitResult {
  committed: number;
  restored: number;
  duplicates: number;
  unresolved: number;
  errors: number;
}

export interface CommissionPreview {
  commission: number;
  gross: number;
}

export interface ApiErrorBody {
  detail: string;
}

export interface AuthUser {
  id: number;
  name: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  user: AuthUser;
}
