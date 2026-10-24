import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getPortfolioAdvice,
  getSavedPortfolioAdvice,
  getSavedSchemeAdvice,
  getSchemeAdvice,
} from '../lib/api';
import { formatDateTime } from '../lib/format';
import type { AdviceSource, SchemeHolding } from '../types/api';

function Sources({ sources }: { sources: AdviceSource[] }) {
  if (sources.length === 0) return <p className="advice__muted">No web sources were cited.</p>;
  return (
    <ul className="advice__sources">
      {sources.map((source) => (
        <li key={source.url}>
          <a href={source.url} target="_blank" rel="noreferrer noopener">
            {source.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

function Footer({
  model,
  disclaimer,
  generatedAt,
}: {
  model: string;
  disclaimer: string;
  generatedAt: string | null;
}) {
  return (
    <p className="advice__muted">
      {generatedAt && <strong>Generated {formatDateTime(generatedAt)}. </strong>}
      {disclaimer} <span>Model: {model}.</span>
    </p>
  );
}

export function SchemeAdvicePanel({
  holding,
  onClose,
}: {
  holding: SchemeHolding;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const key = ['advice', 'scheme', holding.scheme_code];
  const saved = useQuery({
    queryKey: key,
    queryFn: () => getSavedSchemeAdvice(holding.scheme_code),
  });
  const run = useMutation({
    mutationFn: () => getSchemeAdvice(holding.scheme_code),
    onSuccess: (result) => queryClient.setQueryData(key, result),
  });
  const autoRan = useRef<string | null>(null);

  useEffect(() => {
    if (saved.isSuccess && saved.data === null && autoRan.current !== holding.scheme_code) {
      autoRan.current = holding.scheme_code;
      run.mutate();
    }
  }, [saved.isSuccess, saved.data, holding.scheme_code, run]);

  const advice = { data: saved.data ?? undefined, isPending: run.isPending, error: run.error };

  return (
    <article className="panel panel--wide advice">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">AI advice · Gemini</p>
          <h3>{holding.display_name}</h3>
        </div>
        <div className="advice__actions">
          <button type="button" className="btn btn--small" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? 'Analysing…' : 'Refresh'}
          </button>
          <button type="button" className="btn btn--small" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      {advice.isPending && !advice.data && (
        <p className="empty-state">Researching this fund; this can take up to a minute.</p>
      )}
      {advice.error && <p className="sync-result sync-result--error">{advice.error.message}</p>}
      {advice.data && (
        <>
          <p>
            <span className={`advice__badge advice__badge--${advice.data.action.toLowerCase()}`}>
              {advice.data.action}
            </span>{' '}
            <span className="advice__muted">Confidence: {advice.data.confidence}</span>
          </p>
          <p>{advice.data.rationale}</p>
          {advice.data.risks.length > 0 && (
            <>
              <h4>Risks</h4>
              <ul>
                {advice.data.risks.map((risk) => <li key={risk}>{risk}</li>)}
              </ul>
            </>
          )}
          <h4>Sources</h4>
          <Sources sources={advice.data.sources} />
          <Footer
            model={advice.data.model}
            disclaimer={advice.data.disclaimer}
            generatedAt={advice.data.generated_at}
          />
        </>
      )}
    </article>
  );
}

export function PortfolioAdvicePanel() {
  const queryClient = useQueryClient();
  const key = ['advice', 'portfolio'];
  const saved = useQuery({ queryKey: key, queryFn: getSavedPortfolioAdvice });
  const run = useMutation({
    mutationFn: getPortfolioAdvice,
    onSuccess: (result) => queryClient.setQueryData(key, result),
  });

  return (
    <article className="panel panel--wide advice">
      <div className="panel__heading">
        <div>
          <p className="eyebrow">AI advice · Gemini</p>
          <h3>Portfolio optimisation</h3>
        </div>
        <button type="button" className="btn btn--primary" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? 'Analysing…' : saved.data ? 'Re-analyse' : 'Analyse portfolio'}
        </button>
      </div>
      {!saved.data && !run.isPending && !run.error && (
        <p className="empty-state">
          Your holdings and transaction history are sent to Google Gemini for analysis when you start a run.
        </p>
      )}
      {run.isPending && !saved.data && (
        <p className="empty-state">Researching your funds; this can take up to a minute.</p>
      )}
      {run.error && <p className="sync-result sync-result--error">{run.error.message}</p>}
      {saved.data && (
        <>
          <p>{saved.data.summary}</p>
          {saved.data.actions.length > 0 && (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Fund</th>
                    <th>Action</th>
                    <th>Suggestion</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {saved.data.actions.map((action, index) => (
                    <tr key={`${action.scheme_code ?? action.scheme_name}-${index}`}>
                      <td>{action.scheme_name}</td>
                      <td>
                        <span className={`advice__badge advice__badge--${action.action.toLowerCase()}`}>
                          {action.action}
                        </span>
                      </td>
                      <td>{action.suggestion}</td>
                      <td>{action.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {saved.data.diversification_notes.length > 0 && (
            <>
              <h4>Diversification</h4>
              <ul>
                {saved.data.diversification_notes.map((note) => <li key={note}>{note}</li>)}
              </ul>
            </>
          )}
          <h4>Sources</h4>
          <Sources sources={saved.data.sources} />
          <Footer
            model={saved.data.model}
            disclaimer={saved.data.disclaimer}
            generatedAt={saved.data.generated_at}
          />
        </>
      )}
    </article>
  );
}