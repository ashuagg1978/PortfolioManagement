import { useMemo, useState } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table';
import type { SchemeHolding } from '../types/api';
import { formatCurrency, formatNav, formatPercent, formatUnits, formatXirr } from '../lib/format';

const columnHelper = createColumnHelper<SchemeHolding>();

const columns = [
  columnHelper.accessor('display_name', { header: 'Display Scheme' }),
  columnHelper.accessor('net_units', {
    header: 'Net Units',
    cell: (c) => formatUnits(c.getValue()),
  }),
  columnHelper.accessor('net_invested', {
    header: 'Net Invested',
    cell: (c) => formatCurrency(c.getValue()),
  }),
  columnHelper.accessor('avg_cost_nav', {
    header: 'Avg Cost NAV',
    cell: (c) => (c.getValue() === null ? '—' : formatNav(c.getValue()!)),
  }),
  columnHelper.accessor('latest_nav', {
    header: 'Latest NAV',
    cell: (c) => (c.getValue() === null ? '—' : formatNav(c.getValue()!)),
  }),
  columnHelper.accessor('current_value', {
    header: 'Current Value',
    cell: (c) => formatCurrency(c.getValue()),
  }),
  columnHelper.accessor('total_gain', {
    header: 'Gain/Loss',
    cell: (c) => (
      <span className={c.getValue() >= 0 ? 'positive' : 'negative'}>{formatCurrency(c.getValue())}</span>
    ),
  }),
  columnHelper.accessor('pct_gain', {
    header: '% Gain',
    cell: (c) => (
      <span className={(c.getValue() ?? 0) >= 0 ? 'positive' : 'negative'}>{formatPercent(c.getValue())}</span>
    ),
  }),
  columnHelper.accessor('status', {
    header: 'Status',
    cell: (c) => <span className={`status-pill status-pill--${c.getValue().replace(/\s+/g, '-').toLowerCase()}`}>{c.getValue()}</span>,
  }),
  columnHelper.accessor('xirr', {
    header: 'XIRR',
    cell: (c) => (
      <span className={(c.getValue() ?? 0) >= 0 ? 'positive' : 'negative'}>{formatXirr(c.getValue())}</span>
    ),
  }),
];

export default function HoldingsTable({ holdings }: { holdings: SchemeHolding[] }) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'current_value', desc: true }]);
  const data = useMemo(() => holdings, [holdings]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (holdings.length === 0) {
    return <p className="empty-state">No holdings yet - add a transaction or import your statement.</p>;
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} onClick={header.column.getToggleSortingHandler()} className="sortable">
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {{ asc: ' ▲', desc: ' ▼' }[header.column.getIsSorted() as string] ?? ''}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
