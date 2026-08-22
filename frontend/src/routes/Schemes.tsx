import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { searchSchemes } from '../lib/api';
import { formatDate, formatNav } from '../lib/format';

const PAGE_SIZE = 50;

export default function Schemes() {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const trimmed = debounced.trim();
  const {
    data: results = [],
    isFetching,
    isError,
  } = useQuery({
    queryKey: ['schemes', 'browse', trimmed],
    queryFn: () => searchSchemes(trimmed, PAGE_SIZE),
    enabled: trimmed.length >= 2,
  });

  return (
    <div className="page">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Reference</p>
          <h2>Schemes</h2>
          <p className="hero-copy">
            Search the AMFI scheme master by a few words of the name, or by scheme code. Useful for
            looking up the exact code before entering a transaction, or checking a fund's latest
            synced NAV. Results only cover schemes that have been through at least one{' '}
            <strong>Sync NAV</strong>.
          </p>
        </div>
      </section>

      <section className="panel">
        <input
          type="text"
          className="schemes-search-box"
          placeholder="Search by scheme name (a few words, any order) or code…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />

        {trimmed.length < 2 && <p className="hint">Type at least 2 characters to search.</p>}
        {isFetching && <p className="hint">Searching…</p>}
        {isError && <p className="form-error">Search failed - is the backend running?</p>}
        {!isFetching && trimmed.length >= 2 && results.length === 0 && !isError && (
          <p className="empty-state">
            No matches for "{trimmed}". If this scheme should exist, click <strong>Sync NAV</strong> on
            the Dashboard first.
          </p>
        )}

        {results.length > 0 && (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Scheme Code</th>
                  <th>Scheme Name</th>
                  <th>Plan</th>
                  <th>Option</th>
                  <th>Latest NAV</th>
                  <th>NAV Date</th>
                </tr>
              </thead>
              <tbody>
                {results.map((s) => (
                  <tr key={s.scheme_code}>
                    <td className="schemes-table__code">{s.scheme_code}</td>
                    <td>{s.scheme_name}</td>
                    <td>{s.plan ?? '—'}</td>
                    <td>{s.option ?? '—'}</td>
                    <td>{s.latest_nav !== null ? formatNav(s.latest_nav) : '—'}</td>
                    <td>{s.nav_date ? formatDate(s.nav_date) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {results.length === PAGE_SIZE && (
              <p className="hint">Showing the first {PAGE_SIZE} matches - narrow your search for more specific results.</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
