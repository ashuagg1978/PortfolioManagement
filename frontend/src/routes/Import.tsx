import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  API_BASE,
  ApiError,
  commitImportBatch,
  getImportBatch,
  getImportRows,
  listAccounts,
  mapImportScheme,
  uploadImport,
} from '../lib/api';
import { formatCurrency, formatDate, formatNav, formatUnits } from '../lib/format';
import SchemeCodeField from '../components/SchemeCodeField';
import SchemeSearchInput from '../components/SchemeSearchInput';
import type { CommitResult } from '../types/api';

export default function Import() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [accountId, setAccountId] = useState('');
  const [batchId, setBatchId] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [commitResult, setCommitResult] = useState<CommitResult | null>(null);
  const [schemeChoices, setSchemeChoices] = useState<Record<string, string>>({});
  const [schemeLabels, setSchemeLabels] = useState<Record<string, string>>({});

  const { data: accounts = [] } = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });
  const { data: batch, isLoading } = useQuery({
    queryKey: ['imports', batchId],
    queryFn: () => getImportBatch(batchId!),
    enabled: batchId !== null,
  });
  const { data: rows = [] } = useQuery({
    queryKey: ['imports', batchId, 'rows'],
    queryFn: () => getImportRows(batchId!),
    enabled: batchId !== null,
  });

  const upload = useMutation({
    mutationFn: ({ file, accountId }: { file: File; accountId: number }) => uploadImport(file, accountId),
    onSuccess: (result) => {
      setBatchId(result.id);
      setUploadError(null);
      setCommitResult(null);
      setSchemeChoices({});
    },
    onError: (err) => setUploadError(err instanceof ApiError ? err.message : 'Upload failed.'),
  });

  const mapScheme = useMutation({
    mutationFn: ({ key, schemeCode }: { key: string; schemeCode: string }) =>
      mapImportScheme(batchId!, key, schemeCode),
    onSuccess: (result) => {
      queryClient.setQueryData(['imports', batchId], result);
      queryClient.invalidateQueries({ queryKey: ['imports', batchId, 'rows'] });
    },
  });

  const commit = useMutation({
    mutationFn: () => commitImportBatch(batchId!),
    onSuccess: (result) => {
      setCommitResult(result);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['imports', batchId] });
      queryClient.invalidateQueries({ queryKey: ['imports', batchId, 'rows'] });
    },
  });

  const canCommit = batch !== undefined && batch.status === 'PENDING' && batch.unmapped_scheme_keys.length === 0;

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Step 1</p>
            <h3>Choose an account, then upload a statement</h3>
          </div>
          <a className="btn" href={`${API_BASE}/api/imports/template`} download>
            ⬇ Download bulk upload template
          </a>
        </div>
        <p className="hint">
          Every row in the file is imported into the one account you pick here - use a separate
          upload per account. Rows are parsed and staged for review; nothing is written to your
          ledger until you commit.
        </p>

        <table className="form-table">
          <tbody>
            <tr>
              <td className="form-table__label">Account</td>
              <td>
                <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="">Select…</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.account_name}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
            <tr>
              <td className="form-table__label">File</td>
              <td>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx"
                  disabled={!accountId}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file && accountId) upload.mutate({ file, accountId: Number(accountId) });
                  }}
                />
                {!accountId && <p className="hint">Pick an account first.</p>}
              </td>
            </tr>
          </tbody>
        </table>

        {upload.isPending && <p className="hint">Parsing…</p>}
        {uploadError && <p className="form-error">{uploadError}</p>}
      </section>

      {batch && (
        <>
          <section className="panel">
            <div className="panel__heading">
              <div>
                <p className="eyebrow">Step 2</p>
                <h3>
                  Review - {batch.filename} → {batch.account_name}
                </h3>
              </div>
            </div>

            {batch.sheet_used && (
              <p className="hint">
                Read from sheet "{batch.sheet_used}".
                {batch.other_sheets_ignored.length > 0 && (
                  <>
                    {' '}
                    This file also has {batch.other_sheets_ignored.length} other sheet(s) that look like
                    transaction tables ({batch.other_sheets_ignored.join(', ')}) - only the first is
                    imported per upload. Re-upload this file again, once per remaining sheet, if they
                    hold data you need too.
                  </>
                )}
              </p>
            )}

            <div className="summary-grid summary-grid--compact">
              <div className="kpi-card">
                <p className="kpi-card__title">Total rows</p>
                <p className="kpi-card__value">{batch.row_count}</p>
              </div>
              {Object.entries(batch.action_counts).map(([action, count]) => (
                <div className="kpi-card" key={action}>
                  <p className="kpi-card__title">{action}</p>
                  <p className="kpi-card__value">{count}</p>
                </div>
              ))}
            </div>

            {batch.unmapped_scheme_keys.length > 0 && (
              <div className="mapping-block">
                <h4>Unmapped schemes</h4>
                <p className="hint">
                  These couldn't be resolved to an AMFI scheme automatically - possibly a renamed or
                  merged fund, or a scheme code that hasn't been synced yet. Search for the right
                  scheme, or type/verify a code directly.
                </p>
                {batch.unmapped_scheme_keys.map((key) => (
                  <div className="mapping-row" key={key}>
                    <span>{key}</span>
                    <div className="mapping-row__fields">
                      <SchemeSearchInput
                        value={schemeChoices[key] ?? ''}
                        onSelect={(s) => {
                          setSchemeChoices((prev) => ({ ...prev, [key]: s.scheme_code }));
                          setSchemeLabels((prev) => ({ ...prev, [key]: s.scheme_name }));
                          mapScheme.mutate({ key, schemeCode: s.scheme_code });
                        }}
                      />
                      <SchemeCodeField
                        code={schemeChoices[key] ?? ''}
                        label={schemeLabels[key] ?? ''}
                        onResolved={(s) => {
                          setSchemeChoices((prev) => ({ ...prev, [key]: s.scheme_code }));
                          setSchemeLabels((prev) => ({ ...prev, [key]: s.scheme_name }));
                          mapScheme.mutate({ key, schemeCode: s.scheme_code });
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {isLoading && <p className="hint">Refreshing…</p>}
          </section>

          <section className="panel panel--wide">
            <div className="panel__heading">
              <div>
                <p className="eyebrow">All parsed entries</p>
                <h3>
                  {rows.length} row{rows.length === 1 ? '' : 's'}
                </h3>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Scheme code</th>
                    <th>Scheme name</th>
                    <th>Folio</th>
                    <th>NAV</th>
                    <th>Units</th>
                    <th>Amount</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>{r.row_index}</td>
                      <td>{r.transaction_date ? formatDate(r.transaction_date) : '—'}</td>
                      <td>{r.type ?? '—'}</td>
                      <td>{r.resolved_scheme_code ?? r.scheme_code_hint ?? '—'}</td>
                      <td>{r.raw_scheme_name ?? '—'}</td>
                      <td>{r.folio_no ?? '—'}</td>
                      <td>{r.nav !== null ? formatNav(r.nav) : '—'}</td>
                      <td>{r.units !== null ? formatUnits(r.units) : '—'}</td>
                      <td>{r.amount !== null ? formatCurrency(r.amount) : '—'}</td>
                      <td>
                        <span className={`status-pill status-pill--${r.action.toLowerCase()}`}>{r.action}</span>
                        {r.error && <p className="form-error form-error--inline">{r.error}</p>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel__heading">
              <div>
                <p className="eyebrow">Step 3</p>
                <h3>Commit</h3>
              </div>
            </div>
            {batch.status === 'COMMITTED' ? (
              <p className="hint">This batch has already been committed.</p>
            ) : (
              <>
                <button className="btn btn--primary" onClick={() => commit.mutate()} disabled={!canCommit || commit.isPending}>
                  {commit.isPending ? 'Committing…' : 'Commit to ledger'}
                </button>
                {!canCommit && <p className="hint">Resolve every unmapped scheme above first.</p>}
              </>
            )}
            {commitResult && (
              <div className="summary-grid summary-grid--compact">
                <div className="kpi-card">
                  <p className="kpi-card__title">Committed</p>
                  <p className="kpi-card__value kpi-card__value--positive">{commitResult.committed}</p>
                </div>
                <div className="kpi-card">
                  <p className="kpi-card__title">Restored</p>
                  <p className="kpi-card__value kpi-card__value--positive">{commitResult.restored}</p>
                </div>
                <div className="kpi-card">
                  <p className="kpi-card__title">Duplicates skipped</p>
                  <p className="kpi-card__value">{commitResult.duplicates}</p>
                </div>
                <div className="kpi-card">
                  <p className="kpi-card__title">Unresolved</p>
                  <p className="kpi-card__value">{commitResult.unresolved}</p>
                </div>
                <div className="kpi-card">
                  <p className="kpi-card__title">Errors</p>
                  <p className="kpi-card__value kpi-card__value--negative">{commitResult.errors}</p>
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
