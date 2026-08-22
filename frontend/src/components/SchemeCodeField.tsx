import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { searchSchemes } from '../lib/api';
import type { SchemeSearchResult } from '../types/api';

interface SchemeCodeFieldProps {
  code: string;
  label: string; // the resolved scheme's name, shown as a confirmation line
  onResolved: (scheme: SchemeSearchResult) => void;
}

/**
 * A separate, explicit field for the AMFI scheme code - deliberately not
 * just a caption under the name search box. Getting the code wrong is the
 * one mistake that silently corrupts a scheme's whole history (AMFI names
 * are not unique - see DATABASE.md#schemes), so this field:
 *   - always shows the resolved code, never hidden behind an open/closed state
 *   - is itself editable: paste/type a code directly and it's verified
 *     against the schemes table on blur/Enter, independent of the name search
 *   - shows the matched scheme's name back as confirmation, so a mistyped
 *     or wrong code is visible before the form is ever submitted
 */
export default function SchemeCodeField({ code, label, onResolved }: SchemeCodeFieldProps) {
  const [draft, setDraft] = useState(code);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(code);
    setError(null);
  }, [code]);

  const lookup = useMutation({
    mutationFn: (c: string) => searchSchemes(c),
    onSuccess: (results, c) => {
      const exact = results.find((r) => r.scheme_code === c.trim());
      if (exact) {
        setError(null);
        onResolved(exact);
      } else {
        setError(`No scheme with code "${c}" - try the search box above, or Sync NAV first if it's new.`);
      }
    },
    onError: () => setError('Lookup failed - is the backend running?'),
  });

  function verify() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === code) return;
    lookup.mutate(trimmed);
  }

  return (
    <div className="scheme-code-field">
      <input
        type="text"
        className="scheme-code-field__input"
        value={draft}
        placeholder="e.g. 103196"
        onChange={(e) => setDraft(e.target.value)}
        onBlur={verify}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            verify();
          }
        }}
      />
      {lookup.isPending && <p className="scheme-code-field__status">Verifying…</p>}
      {!lookup.isPending && !error && code && draft.trim() === code && (
        <p className="scheme-code-field__status scheme-code-field__status--ok">✓ {label}</p>
      )}
      {error && <p className="scheme-code-field__status scheme-code-field__status--error">{error}</p>}
    </div>
  );
}
