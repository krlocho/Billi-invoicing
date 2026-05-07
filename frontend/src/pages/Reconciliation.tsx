import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  XCircle,
  Clock,
  Brain,
  ArrowRight,
  Loader2,
  ChevronDown,
  ChevronUp,
  Building2,
  CreditCard,
  Search,
  AlertTriangle,
  Sparkles,
} from 'lucide-react';
import {
  getReconciliation,
  getMatches,
  getUnmatchedTransactions,
  updateMatch,
  confirmAllHigh,
  generateInvoices,
} from '../services/api';

interface BankTx {
  id: string;
  transaction_date: string;
  description: string;
  amount: number;
  detected_channel: string | null;
}

interface Reservation {
  id: string;
  guest_name: string | null;
  channel: string | null;
  checkin_date: string | null;
  checkout_date: string | null;
  nights: number | null;
  gross_amount: number | null;
  net_amount: number | null;
  currency: string | null;
}

interface Match {
  id: string;
  bank_transaction_id: string;
  confidence_score: number | null;
  confidence_tier: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  amount_difference: number | null;
  match_type: string | null;
  status: 'pending' | 'confirmed' | 'rejected' | string;
  match_details: any;
  reservation_ids: string[];
  bank_transaction: BankTx | null;
  reservations: Reservation[];
}

interface UnmatchedTx {
  id: string;
  transaction_date: string;
  description: string;
  amount: number;
  detected_channel: string | null;
}

type TabKey = 'all' | 'pending' | 'confirmed' | 'rejected' | 'unmatched';
type TierFilter = 'ALL' | 'HIGH' | 'MEDIUM' | 'LOW';

const fmtMoney = (n: number | null | undefined, ccy = 'EUR') =>
  n == null ? '—' : `${n.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${ccy}`;

const fmtDate = (s: string | null | undefined) => {
  if (!s) return '—';
  const [y, m, d] = s.split('-');
  return `${d}/${m}/${y}`;
};

const channelTone = (name: string | null | undefined) => {
  const n = (name || '').toLowerCase();
  if (n.includes('booking')) return 'bg-blue-50 text-blue-700 border-blue-200';
  if (n.includes('airbnb')) return 'bg-rose-50 text-rose-700 border-rose-200';
  if (n.includes('expedia')) return 'bg-amber-50 text-amber-700 border-amber-200';
  if (n.includes('stripe')) return 'bg-violet-50 text-violet-700 border-violet-200';
  return 'bg-gray-50 text-gray-700 border-gray-200';
};

const tierTone = (tier: string) => {
  switch (tier) {
    case 'HIGH': return 'bg-green-50 text-green-700 border-green-200';
    case 'MEDIUM': return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'LOW': return 'bg-red-50 text-red-700 border-red-200';
    default: return 'bg-gray-50 text-gray-700 border-gray-200';
  }
};

const tierLabel = (tier: string) =>
  tier === 'HIGH' ? 'Alta' : tier === 'MEDIUM' ? 'Media' : tier === 'LOW' ? 'Baja' : tier;

export default function Reconciliation() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rec, setRec] = useState<any>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [unmatched, setUnmatched] = useState<UnmatchedTx[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<TabKey>('all');
  const [tierFilter, setTierFilter] = useState<TierFilter>('ALL');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    if (!id) return;
    const [recRes, matchRes, unmatchedRes] = await Promise.all([
      getReconciliation(id),
      getMatches(id),
      getUnmatchedTransactions(id).catch(() => ({ data: [] as UnmatchedTx[] })),
    ]);
    setRec(recRes.data);
    setMatches(matchRes.data || []);
    setUnmatched(unmatchedRes.data || []);
    setLoading(false);
  };

  useEffect(() => {
    if (!id) return;
    let stopped = false;
    const tick = async () => {
      try {
        const recRes = await getReconciliation(id);
        if (stopped) return;
        setRec(recRes.data);
        if (recRes.data.status === 'completed' || recRes.data.status === 'failed') {
          await refresh();
          return;
        }
      } catch {
        // ignore
      }
      setTimeout(tick, 2000);
    };
    tick();
    return () => {
      stopped = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const toggle = (mid: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(mid)) next.delete(mid);
      else next.add(mid);
      return next;
    });
  };

  const filtered = useMemo(() => {
    let list = matches;
    if (tab !== 'all' && tab !== 'unmatched') {
      list = list.filter((m) => m.status === tab);
    }
    if (tierFilter !== 'ALL') {
      list = list.filter((m) => m.confidence_tier === tierFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((m) => {
        const fields = [
          m.bank_transaction?.description || '',
          m.bank_transaction?.detected_channel || '',
          ...m.reservations.map((r) => r.guest_name || ''),
          ...m.reservations.map((r) => r.channel || ''),
        ].join(' ').toLowerCase();
        return fields.includes(q);
      });
    }
    return list;
  }, [matches, tab, tierFilter, search]);

  const counts = useMemo(() => ({
    all: matches.length,
    pending: matches.filter((m) => m.status === 'pending').length,
    confirmed: matches.filter((m) => m.status === 'confirmed').length,
    rejected: matches.filter((m) => m.status === 'rejected').length,
    unmatched: unmatched.length,
  }), [matches, unmatched]);

  const handleAction = async (matchId: string, status: 'confirmed' | 'rejected') => {
    if (!id) return;
    setBusy(true);
    try {
      await updateMatch(id, matchId, { status });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmAll = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await confirmAllHigh(id);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmVisible = async () => {
    if (!id) return;
    const targets = filtered.filter((m) => m.status === 'pending');
    if (targets.length === 0) return;
    if (!confirm(`Confirmar ${targets.length} matches visibles?`)) return;
    setBusy(true);
    try {
      for (const m of targets) await updateMatch(id, m.id, { status: 'confirmed' });
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateInvoices = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await generateInvoices(id);
      navigate('/app/invoices');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Loader2 className="w-10 h-10 text-violet-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Cargando conciliación...</p>
        </div>
      </div>
    );
  }

  const isRunning = rec && (rec.status === 'pending' || rec.status === 'running');

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Revisión de conciliación</h1>
          <p className="text-gray-500 mt-1 text-sm">
            Revisa cada match propuesto por la IA. Compara la transacción del banco con la(s) reserva(s) y confirma o rechaza.
          </p>
        </div>
        {rec?.status === 'completed' && (
          <div className="flex gap-2 shrink-0">
            <a
              href={`/app/labeling/${id}`}
              className="text-sm bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 px-4 py-2 rounded-lg font-medium inline-flex items-center"
            >
              Etiquetar para evaluación
            </a>
            <button
              onClick={handleConfirmAll}
              disabled={busy}
              className="text-sm bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 px-4 py-2 rounded-lg font-medium disabled:opacity-50"
            >
              Confirmar todas las HIGH
            </button>
            <button
              onClick={handleGenerateInvoices}
              disabled={busy || counts.confirmed === 0}
              className="text-sm bg-violet-600 hover:bg-violet-700 disabled:bg-gray-300 text-white px-4 py-2 rounded-lg font-medium flex items-center gap-2"
            >
              Generar {counts.confirmed} factura{counts.confirmed === 1 ? '' : 's'} <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Status banner while running */}
      {isRunning && (
        <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 mb-6 flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-violet-600 animate-spin" />
          <div>
            <div className="font-medium text-violet-900">La IA está analizando tus datos…</div>
            <div className="text-xs text-violet-700">Esto puede tardar 10–60 s según el volumen.</div>
          </div>
        </div>
      )}

      {/* Stats */}
      {rec?.status === 'completed' && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <StatCard label="Transacciones" value={rec.total_transactions ?? counts.all + counts.unmatched} tone="gray" />
          <StatCard label="Matches" value={counts.all} tone="violet" />
          <StatCard label="Confirmados" value={counts.confirmed} tone="green" />
          <StatCard label="Pendientes" value={counts.pending} tone="amber" />
          <StatCard label="Sin match" value={counts.unmatched} tone="red" />
        </div>
      )}

      {/* Tabs + filters */}
      {rec?.status === 'completed' && (
        <div className="bg-white border border-gray-100 rounded-xl mb-4">
          <div className="flex flex-wrap items-center gap-2 p-3 border-b border-gray-100">
            <Tab active={tab === 'all'} onClick={() => setTab('all')}>Todos <span className="text-xs opacity-60">{counts.all}</span></Tab>
            <Tab active={tab === 'pending'} onClick={() => setTab('pending')}>Pendientes <span className="text-xs opacity-60">{counts.pending}</span></Tab>
            <Tab active={tab === 'confirmed'} onClick={() => setTab('confirmed')}>Confirmados <span className="text-xs opacity-60">{counts.confirmed}</span></Tab>
            <Tab active={tab === 'rejected'} onClick={() => setTab('rejected')}>Rechazados <span className="text-xs opacity-60">{counts.rejected}</span></Tab>
            <Tab active={tab === 'unmatched'} onClick={() => setTab('unmatched')}>Sin match <span className="text-xs opacity-60">{counts.unmatched}</span></Tab>
          </div>
          {tab !== 'unmatched' && (
            <div className="flex flex-wrap items-center gap-3 p-3">
              <div className="flex gap-1">
                {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as TierFilter[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTierFilter(t)}
                    className={`text-xs px-2.5 py-1 rounded-full font-medium border transition-colors ${
                      tierFilter === t
                        ? t === 'ALL'
                          ? 'bg-gray-900 text-white border-gray-900'
                          : tierTone(t).replace('bg-', 'bg-').replace(/text-(\w+)-(\d+)/, 'text-$1-800') + ' ring-1 ring-offset-1'
                        : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {t === 'ALL' ? 'Todas' : tierLabel(t)}
                  </button>
                ))}
              </div>
              <div className="relative flex-1 min-w-[200px]">
                <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar por huésped, canal, descripción…"
                  className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                />
              </div>
              <button
                onClick={handleConfirmVisible}
                disabled={busy || filtered.filter((m) => m.status === 'pending').length === 0}
                className="text-xs bg-green-600 hover:bg-green-700 disabled:bg-gray-300 text-white px-3 py-1.5 rounded-lg font-medium flex items-center gap-1"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Confirmar visibles ({filtered.filter((m) => m.status === 'pending').length})
              </button>
            </div>
          )}
        </div>
      )}

      {/* Content */}
      {tab === 'unmatched' ? (
        <UnmatchedList items={unmatched} />
      ) : (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-100 py-16 text-center">
              <p className="text-gray-500 text-sm">No hay matches con estos filtros.</p>
            </div>
          ) : (
            filtered.map((m) => (
              <MatchCard
                key={m.id}
                match={m}
                expanded={expanded.has(m.id)}
                onToggle={() => toggle(m.id)}
                onConfirm={() => handleAction(m.id, 'confirmed')}
                onReject={() => handleAction(m.id, 'rejected')}
                busy={busy}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number | string; tone: 'gray' | 'violet' | 'green' | 'amber' | 'red' }) {
  const tones: Record<string, string> = {
    gray: 'bg-gray-50 text-gray-900',
    violet: 'bg-violet-50 text-violet-900',
    green: 'bg-green-50 text-green-900',
    amber: 'bg-amber-50 text-amber-900',
    red: 'bg-red-50 text-red-900',
  };
  return (
    <div className={`rounded-xl p-4 ${tones[tone]}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs opacity-70 mt-0.5">{label}</div>
    </div>
  );
}

function Tab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5 ${
        active ? 'bg-violet-100 text-violet-700' : 'text-gray-600 hover:bg-gray-50'
      }`}
    >
      {children}
    </button>
  );
}

function MatchCard({
  match,
  expanded,
  onToggle,
  onConfirm,
  onReject,
  busy,
}: {
  match: Match;
  expanded: boolean;
  onToggle: () => void;
  onConfirm: () => void;
  onReject: () => void;
  busy: boolean;
}) {
  const tx = match.bank_transaction;
  const reservedTotal = match.reservations.reduce((s, r) => s + (r.gross_amount || 0), 0);
  const ccy = match.reservations[0]?.currency || 'EUR';

  const StatusIcon = match.status === 'confirmed'
    ? <CheckCircle2 className="w-5 h-5 text-green-500" />
    : match.status === 'rejected'
      ? <XCircle className="w-5 h-5 text-red-500" />
      : <Clock className="w-5 h-5 text-amber-500" />;

  return (
    <div className={`bg-white rounded-xl border ${expanded ? 'border-violet-200 shadow-sm' : 'border-gray-100'} overflow-hidden transition-all`}>
      {/* Summary row */}
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-3 hover:bg-gray-50 flex items-center gap-4"
      >
        {/* Left: icon */}
        <div className="shrink-0">{StatusIcon}</div>
        {/* Date / amount */}
        <div className="shrink-0 w-28 text-xs">
          <div className="font-mono text-gray-900">{fmtDate(tx?.transaction_date)}</div>
          <div className="font-semibold text-gray-900">{fmtMoney(tx?.amount, 'EUR')}</div>
        </div>
        {/* Bank desc */}
        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-500 truncate">{tx?.description || '—'}</div>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {match.reservations.slice(0, 3).map((r) => (
              <span key={r.id} className="text-xs text-gray-600 truncate max-w-[140px]">
                {r.guest_name || 'sin nombre'}
              </span>
            ))}
            {match.reservations.length > 3 && (
              <span className="text-xs text-gray-400">+{match.reservations.length - 3}</span>
            )}
          </div>
        </div>
        {/* Channel */}
        {match.reservations[0]?.channel && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium border shrink-0 ${channelTone(match.reservations[0].channel)}`}>
            {match.reservations[0].channel}
          </span>
        )}
        {/* Tier */}
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium border shrink-0 ${tierTone(match.confidence_tier)}`}>
          {tierLabel(match.confidence_tier)} · {match.confidence_score ? Math.round(match.confidence_score * 100) : 0}%
        </span>
        <div className="shrink-0">
          {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
        </div>
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50">
          {/* Side-by-side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-x divide-gray-100">
            {/* Bank tx */}
            <div className="p-4">
              <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                <CreditCard className="w-3.5 h-3.5" /> Banco
              </div>
              <div className="space-y-2 text-sm">
                <Row label="Fecha" value={fmtDate(tx?.transaction_date)} mono />
                <Row label="Importe" value={fmtMoney(tx?.amount)} bold />
                <Row label="Concepto" value={tx?.description || '—'} multiline />
                {tx?.detected_channel && (
                  <Row label="Canal detectado" value={tx.detected_channel} />
                )}
              </div>
            </div>
            {/* Reservations */}
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  <Building2 className="w-3.5 h-3.5" />
                  Reserva{match.reservations.length === 1 ? '' : `s (${match.reservations.length})`}
                </div>
                <div className="text-xs text-gray-500">
                  Total: <span className="font-semibold text-gray-900">{fmtMoney(reservedTotal, ccy)}</span>
                </div>
              </div>
              <div className="space-y-3">
                {match.reservations.map((r) => (
                  <div key={r.id} className="bg-white rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-medium text-sm text-gray-900">{r.guest_name || 'Sin nombre'}</div>
                      {r.channel && (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium border ${channelTone(r.channel)}`}>
                          {r.channel}
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
                      <div><span className="text-gray-400">Check-in:</span> {fmtDate(r.checkin_date)}</div>
                      <div><span className="text-gray-400">Check-out:</span> {fmtDate(r.checkout_date)}</div>
                      <div><span className="text-gray-400">Noches:</span> {r.nights ?? '—'}</div>
                      <div><span className="text-gray-400">Bruto:</span> {fmtMoney(r.gross_amount, r.currency || 'EUR')}</div>
                      <div className="col-span-2"><span className="text-gray-400">Neto:</span> {fmtMoney(r.net_amount, r.currency || 'EUR')}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Diff + reasoning + actions */}
          <div className="px-4 pb-4 pt-2 space-y-3">
            {match.amount_difference !== null && match.amount_difference !== undefined && (
              <div className={`flex items-center gap-2 text-sm rounded-lg p-2.5 ${
                Math.abs(match.amount_difference) < 1
                  ? 'bg-green-50 text-green-800'
                  : Math.abs(match.amount_difference) < 10
                    ? 'bg-amber-50 text-amber-800'
                    : 'bg-red-50 text-red-800'
              }`}>
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>
                  Diferencia banco vs reservas (neto): <span className="font-semibold">{fmtMoney(match.amount_difference)}</span>
                </span>
              </div>
            )}

            {match.match_details?.reasoning && (
              <div className="bg-violet-50 border border-violet-100 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-violet-700 mb-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> Razonamiento de la IA
                </div>
                <p className="text-sm text-violet-900 leading-relaxed">{match.match_details.reasoning}</p>
                {(match.match_details.commission_rate != null
                  || match.match_details.learned_commission_rate != null
                  || match.match_details.llm_confidence != null) && (
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {match.match_details.learned_commission_rate != null ? (
                      <span className="bg-white px-2 py-0.5 rounded border border-emerald-300 text-emerald-800">
                        Comisión aprendida: {(match.match_details.learned_commission_rate * 100).toFixed(2)}%
                        {match.match_details.learned_commission_samples
                          ? ` · ${match.match_details.learned_commission_samples} matches`
                          : ''}
                      </span>
                    ) : match.match_details.commission_rate != null && (
                      <span className="bg-white px-2 py-0.5 rounded border border-violet-200 text-violet-800">
                        Comisión LLM: {(match.match_details.commission_rate * 100).toFixed(1)}%
                      </span>
                    )}
                    {match.match_details.llm_confidence != null && (
                      <span className="bg-white px-2 py-0.5 rounded border border-violet-200 text-violet-800">
                        LLM conf: {(match.match_details.llm_confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {match.status === 'pending' && (
              <div className="flex gap-2 pt-1">
                <button
                  onClick={onConfirm}
                  disabled={busy}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium"
                >
                  <CheckCircle2 className="w-4 h-4" /> Confirmar
                </button>
                <button
                  onClick={onReject}
                  disabled={busy}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-2 bg-white hover:bg-red-50 border border-gray-200 hover:border-red-200 text-red-700 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  <XCircle className="w-4 h-4" /> Rechazar
                </button>
              </div>
            )}
            {match.status === 'confirmed' && (
              <div className="text-xs text-green-700 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Match confirmado — entrará en la generación de facturas.
              </div>
            )}
            {match.status === 'rejected' && (
              <div className="text-xs text-red-700 flex items-center gap-1.5">
                <XCircle className="w-3.5 h-3.5" /> Match rechazado.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  bold,
  mono,
  multiline,
}: {
  label: string;
  value: string;
  bold?: boolean;
  mono?: boolean;
  multiline?: boolean;
}) {
  return (
    <div className={multiline ? '' : 'flex items-baseline justify-between gap-3'}>
      <div className="text-xs text-gray-500 shrink-0">{label}</div>
      <div className={`text-sm text-gray-900 ${bold ? 'font-semibold' : ''} ${mono ? 'font-mono' : ''} ${multiline ? 'mt-0.5' : 'text-right'}`}>
        {value}
      </div>
    </div>
  );
}

function UnmatchedList({ items }: { items: UnmatchedTx[] }) {
  if (items.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 py-16 text-center">
        <p className="text-gray-500 text-sm">No hay transacciones sin match.</p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 text-sm text-gray-600">
        Estas transacciones del banco no se han emparejado con ninguna reserva. Pueden ser gastos, transferencias internas o cobros sin canal asociado.
      </div>
      <div className="divide-y divide-gray-100">
        {items.map((tx) => (
          <div key={tx.id} className="px-4 py-3 flex items-center gap-4 text-sm">
            <div className="font-mono text-xs text-gray-700 shrink-0 w-24">{fmtDate(tx.transaction_date)}</div>
            <div className={`font-semibold shrink-0 w-28 text-right ${tx.amount < 0 ? 'text-red-700' : 'text-gray-900'}`}>
              {fmtMoney(tx.amount)}
            </div>
            <div className="flex-1 text-gray-700 truncate">{tx.description}</div>
            {tx.detected_channel && (
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium border shrink-0 ${channelTone(tx.detected_channel)}`}>
                {tx.detected_channel}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
