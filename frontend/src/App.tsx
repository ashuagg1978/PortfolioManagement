import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getDueCount } from './lib/api';
import Dashboard from './routes/Dashboard';
import Transactions from './routes/Transactions';
import Sips from './routes/Sips';
import SipEntriesDue from './routes/SipEntriesDue';
import Import from './routes/Import';
import Schemes from './routes/Schemes';
import Accounts from './routes/Accounts';

const SIDEBAR_COLLAPSED_KEY = 'sidebar-collapsed';
const REF_DATA_OPEN_KEY = 'sidebar-ref-data-open';

function readStoredFlag(key: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : raw === 'true';
  } catch {
    return fallback;
  }
}

function DueBadge() {
  const { data } = useQuery({ queryKey: ['sips', 'due', 'count'], queryFn: getDueCount, refetchInterval: 60_000 });
  if (!data || data.count === 0) return null;
  return <span className="nav-badge">{data.count}</span>;
}

interface NavItemProps {
  to: string;
  end?: boolean;
  abbr: string;
  label: string;
  collapsed: boolean;
  badge?: React.ReactNode;
}

function NavItem({ to, end, abbr, label, collapsed, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={({ isActive }) => `sidebar__link${isActive ? ' active' : ''}`}
    >
      <span className="sidebar__icon">{abbr}</span>
      {!collapsed && <span className="sidebar__label">{label}</span>}
      {badge}
    </NavLink>
  );
}

export default function App() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => readStoredFlag(SIDEBAR_COLLAPSED_KEY, false));
  const [refDataOpen, setRefDataOpen] = useState(() => readStoredFlag(REF_DATA_OPEN_KEY, true));

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    } catch {
      // private browsing / storage disabled - collapse state just won't persist
    }
  }, [collapsed]);

  useEffect(() => {
    try {
      window.localStorage.setItem(REF_DATA_OPEN_KEY, String(refDataOpen));
    } catch {
      // same as above
    }
  }, [refDataOpen]);

  const inReferenceData = location.pathname.startsWith('/schemes') || location.pathname.startsWith('/accounts');

  function toggleReferenceData() {
    if (collapsed) {
      // Expanding a group while the whole sidebar is collapsed would have
      // nowhere to show its children - open the sidebar itself first.
      setCollapsed(false);
      setRefDataOpen(true);
    } else {
      setRefDataOpen((open) => !open);
    }
  }

  return (
    <div className={`app-shell${collapsed ? ' app-shell--collapsed' : ''}`}>
      <aside className={`sidebar${collapsed ? ' sidebar--collapsed' : ''}`}>
        <div className="sidebar__header">
          {!collapsed && (
            <div className="sidebar__brand">
              <p className="eyebrow">Portfolio Management</p>
            </div>
          )}
          <button
            type="button"
            className="sidebar__collapse-btn"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '»' : '«'}
          </button>
        </div>

        <nav className="sidebar__nav">
          {!collapsed && <p className="sidebar__section-label">Mutual Funds</p>}

          <NavItem to="/" end abbr="Db" label="Dashboard" collapsed={collapsed} />
          <NavItem to="/transactions" abbr="Tx" label="Transactions" collapsed={collapsed} />
          <NavItem to="/sips" end abbr="SIP" label="SIPs" collapsed={collapsed} />
          <NavItem to="/sips/due" end abbr="Due" label="Entries Due" collapsed={collapsed} badge={<DueBadge />} />
          <NavItem to="/import" abbr="Imp" label="Import" collapsed={collapsed} />

          <button
            type="button"
            className={`sidebar__group-toggle${inReferenceData ? ' sidebar__group-toggle--active' : ''}`}
            onClick={toggleReferenceData}
            title={collapsed ? 'Reference Data' : undefined}
          >
            <span className="sidebar__icon">Ref</span>
            {!collapsed && <span className="sidebar__label">Reference Data</span>}
            {!collapsed && <span className="sidebar__chevron">{refDataOpen ? '▾' : '▸'}</span>}
          </button>
          {!collapsed && refDataOpen && (
            <div className="sidebar__submenu">
              <NavLink to="/schemes" className={({ isActive }) => `sidebar__link sidebar__link--sub${isActive ? ' active' : ''}`}>
                Schemes
              </NavLink>
              <NavLink to="/accounts" className={({ isActive }) => `sidebar__link sidebar__link--sub${isActive ? ' active' : ''}`}>
                Accounts
              </NavLink>
            </div>
          )}
        </nav>
      </aside>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/sips" element={<Sips />} />
          <Route path="/sips/due" element={<SipEntriesDue />} />
          <Route path="/import" element={<Import />} />
          <Route path="/schemes" element={<Schemes />} />
          <Route path="/accounts" element={<Accounts />} />
        </Routes>
      </main>
    </div>
  );
}
