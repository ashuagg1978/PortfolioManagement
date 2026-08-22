import { NavLink, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getDueCount } from './lib/api';
import Dashboard from './routes/Dashboard';
import Transactions from './routes/Transactions';
import Sips from './routes/Sips';
import SipEntriesDue from './routes/SipEntriesDue';
import Import from './routes/Import';
import Schemes from './routes/Schemes';

function DueBadge() {
  const { data } = useQuery({ queryKey: ['sips', 'due', 'count'], queryFn: getDueCount, refetchInterval: 60_000 });
  if (!data || data.count === 0) return null;
  return <span className="nav-badge">{data.count}</span>;
}

export default function App() {
  return (
    <div className="app-shell">
      <header className="top-nav">
        <div className="top-nav__brand">
          <p className="eyebrow">Portfolio Management</p>
          <h1>Mutual Funds</h1>
        </div>
        <nav className="top-nav__links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Dashboard
          </NavLink>
          <NavLink to="/transactions" className={({ isActive }) => (isActive ? 'active' : '')}>
            Transactions
          </NavLink>
          <NavLink to="/sips" end className={({ isActive }) => (isActive ? 'active' : '')}>
            SIPs
          </NavLink>
          <NavLink to="/sips/due" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Entries Due
            <DueBadge />
          </NavLink>
          <NavLink to="/import" className={({ isActive }) => (isActive ? 'active' : '')}>
            Import
          </NavLink>
          <NavLink to="/schemes" className={({ isActive }) => (isActive ? 'active' : '')}>
            Schemes
          </NavLink>
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/sips" element={<Sips />} />
          <Route path="/sips/due" element={<SipEntriesDue />} />
          <Route path="/import" element={<Import />} />
          <Route path="/schemes" element={<Schemes />} />
        </Routes>
      </main>
    </div>
  );
}
