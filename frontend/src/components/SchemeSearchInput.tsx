import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { searchSchemes } from '../lib/api';
import type { SchemeSearchResult } from '../types/api';

interface SchemeSearchInputProps {
  value: string; // selected scheme_code
  onSelect: (scheme: SchemeSearchResult) => void;
  placeholder?: string;
}

export default function SchemeSearchInput({ value, onSelect, placeholder }: SchemeSearchInputProps) {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounce so a fast typist doesn't fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 250);
    return () => clearTimeout(timer);
  }, [query]);

  const trimmed = debouncedQuery.trim();
  const {
    data: results = [],
    isFetching,
    isError,
  } = useQuery({
    queryKey: ['schemes', 'search', trimmed],
    queryFn: () => searchSchemes(trimmed),
    enabled: trimmed.length >= 2,
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const searching = trimmed.length >= 2;
  const showNoMatches = open && searching && !isFetching && !isError && results.length === 0;

  return (
    <div className="scheme-search" ref={containerRef}>
      <input
        type="text"
        value={query}
        placeholder={placeholder ?? 'Search by scheme name or code…'}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      />

      {open && searching && (
        <ul className="scheme-search__results">
          {isFetching && (
            <li className="scheme-search__status">Searching…</li>
          )}
          {isError && (
            <li className="scheme-search__status scheme-search__status--error">
              Search failed - is the backend running?
            </li>
          )}
          {showNoMatches && (
            <li className="scheme-search__status">
              No matches for "{trimmed}". If this scheme should exist, click <strong>Sync NAV</strong>{' '}
              on the Dashboard first - schemes only appear here after at least one sync.
            </li>
          )}
          {!isFetching &&
            results.map((s) => (
              <li
                key={s.scheme_code}
                onClick={() => {
                  onSelect(s);
                  setQuery(s.scheme_name);
                  setOpen(false);
                }}
              >
                <span>{s.scheme_name}</span>
                <span className="scheme-search__meta">
                  {[s.plan, s.option].filter(Boolean).join(' · ') || 'code ' + s.scheme_code}
                </span>
              </li>
            ))}
        </ul>
      )}

      {!value && !open && <p className="scheme-search__hint">Type at least 2 characters to search.</p>}
    </div>
  );
}
