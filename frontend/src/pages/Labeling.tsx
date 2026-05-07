import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Search,
  XCircle,
  ListChecks,
  AlertTriangle,
} from 'lucide-react';
import {
  getLabelingDataset,
  getLabels,
  saveLabel,
  deleteLabel,
} from '../services/api';

interface Tx {
  id: string;
  transaction_date: string;
  description: string;
  amount: number;
}

interface Reservation {
  id: string;
  reservation_id: string | null;
  guest_name: string | null;
  channel: string | null;
  checkin_date: string | null;
  checkout_date: string | null;
  nights: number | null;
  gross_amount: number | null;
  net_amount: number | null;
  currency: string;
}

interface Label {
  id: string;
  bank_transaction_id: string;
  reservation_ids: string[];
  label_type: 'match' | 'no_match';
}

const fmt = (d: string | null) => (d ? new Date(d).toLocaleDateString('es-ES') : '—');
const eur = (n: number | null | undefined, cur = 'EUR') =>
  n == null ? '—' : `${n.toFixed(2)} ${cur}`;

export default function Labeling() {
  const { id } = useParams<{ id: string }>();
  const [txs, setTxs] = useState<Tx[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [activeIdx, setActiveIdx] = useState(0);
  const [selectedRes, setSelectedRes] = useState<Set<string>>(new Set());
  const [resQuery, setResQuery] = useState('');
  const [channelFilter, setChannelFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!id) return;
    Promise.all([getLabelingDataset(id), getLabels(id)])
      .then(([dRes, lRes]) => {
        setTxs(dRes.data.transactions);
        setReservations(dRes.data.reservations);
        const map: Record<string, Label> = {};
        for (const l of lRes.data) map[l.bank_transaction_id] = l;
        setLabels(map);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const activeTx = txs[activeIdx];

  // Sync selection when navigating between txs
  useEffect(() => {
    if (!activeTx) return;
    const existing = labels[activeTx.id];
    setSelectedRes(new Set(existing?.reservation_ids || []));
    setResQuery('');
  }, [activeIdx, activeTx, labels]);

  const channels = useMemo(() => {
    const s = new Set<string>();
    for (const r of reservations) if (r.channel) s.add(r.channel);
    return Array.from(s).sort();
  }, [reservations]);

  const filteredReservations = useMemo(() => {
    const q = resQuery.toLowerCase().trim();
    return reservations.filter((r) => {
      if (channelFilter && r.channel !== channelFilter) return false;
      if (!q) return true;
      const blob = `${r.guest_name || ''} ${r.reservation_id || ''} ${r.channel || ''}`.toLowerCase();
      return blob.includes(q);
    });
  }, [reservations, resQuery, channelFilter]);

  const totalReservationsAmount = useMemo(() => {
    if (selectedRes.size === 0) return { gross: 0, net: 0 };
    let gross = 0;
    let net = 0;
    for (const r of reservations) {
      if (selectedRes.has(r.id)) {
        gross += r.gross_amount || 0;
        net += r.net_amount || 0;
      }
    }
    return { gross, net };
  }, [selectedRes, reservations]);

  const labeledCount = Object.keys(labels).length;
  const matchCount = Object.values(labels).filter((l) => l.label_type === 'match').length;
  const noMatchCount = Object.values(labels).filter((l) => l.label_type === 'no_match').length;
  const progress = txs.length === 0 ? 0 : Math.round((labeledCount / txs.length) * 100);

  // Reservations that have already been used in another tx's match label
  const usedElsewhere = useMemo(() => {
    const used = new Set<string>();
    for (const [txId, l] of Object.entries(labels)) {
      if (txId === activeTx?.id) continue;
      if (l.label_type !== 'match') continue;
      for (const rid of l.reservation_ids) used.add(rid);
    }
    return used;
  }, [labels, activeTx]);

  const goto = (delta: number) => {
    if (!txs.length) return;
    let next = activeIdx + delta;
    next = Math.max(0, Math.min(txs.length - 1, next));
    setActiveIdx(next);
  };

  const toggleRes = (rid: string) => {
    setSelectedRes((prev) => {
      const next = new Set(prev);
      if (next.has(rid)) next.delete(rid);
      else next.add(rid);
      return next;
    });
  };

  const submit = async (labelType: 'match' | 'no_match') => {
    if (!activeTx || !id) return;
    setSaving(true);
    try {
      const res = await saveLabel(id, {
        bank_transaction_id: activeTx.id,
        reservation_ids: labelType === 'match' ? Array.from(selectedRes) : [],
        label_type: labelType,
      });
      setLabels((prev) => ({ ...prev, [activeTx.id]: res.data }));
      // Auto-advance to the next unlabeled tx
      const nextUnlabeled = txs.findIndex(
        (t, i) => i > activeIdx && !labels[t.id] && t.id !== activeTx.id,
      );
      if (nextUnlabeled !== -1) setActiveIdx(nextUnlabeled);
      else if (activeIdx < txs.length - 1) setActiveIdx(activeIdx + 1);
    } finally {
      setSaving(false);
    }
  };

  const clearLabel = async () => {
    if (!activeTx || !id) return;
    setSaving(true);
    try {
      await deleteLabel(id, activeTx.id);
      setLabels((prev) => {
        const next = { ...prev };
        delete next[activeTx.id];
        return next;
      });
      setSelectedRes(new Set());
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-gray-500">Cargando dataset...</div>;
  if (!txs.length) return <div className="text-gray-500">No hay transacciones para etiquetar</div>;

  return (
    <div className="-m-8 h-screen flex flex-col">
      <Header
        progress={progress}
        labeled={labeledCount}
        total={txs.length}
        matches={matchCount}
        noMatches={noMatchCount}
      />

      <div className="flex-1 grid grid-cols-12 overflow-hidden">
        {/* Left: tx list */}
        <aside className="col-span-3 border-r border-gray-100 overflow-y-auto bg-white">
          {txs.map((t, i) => {
            const lab = labels[t.id];
            return (
              <button
                key={t.id}
                onClick={() => setActiveIdx(i)}
                className={`w-full text-left px-3 py-2.5 border-b border-gray-50 text-xs ${
                  i === activeIdx ? 'bg-violet-50' : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span className="font-mono text-gray-500">{i + 1}</span>
                  <LabelBadge label={lab?.label_type} />
                </div>
                <div className="font-medium text-gray-900 tabular-nums">
                  {t.amount.toFixed(2)} EUR
                </div>
                <div className="text-gray-500 truncate">{t.description}</div>
                <div className="text-gray-400 text-[10px] mt-0.5">{t.transaction_date}</div>
              </button>
            );
          })}
        </aside>

        {/* Center: active tx + actions */}
        <main className="col-span-5 overflow-y-auto p-6 bg-gray-50">
          <div className="flex items-center gap-2 mb-4">
            <button
              className="p-2 rounded hover:bg-white border border-gray-200"
              onClick={() => goto(-1)}
              disabled={activeIdx === 0}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="text-sm text-gray-500">
              Transacción <b>{activeIdx + 1}</b> de {txs.length}
            </div>
            <button
              className="p-2 rounded hover:bg-white border border-gray-200"
              onClick={() => goto(1)}
              disabled={activeIdx === txs.length - 1}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {activeTx && (
            <div className="bg-white rounded-xl border border-gray-100 p-5 mb-5">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                Transacción bancaria
              </div>
              <div className="flex items-baseline justify-between mb-2">
                <div className="text-2xl font-bold text-gray-900 tabular-nums">
                  {activeTx.amount.toFixed(2)} EUR
                </div>
                <div className="text-sm text-gray-500">{activeTx.transaction_date}</div>
              </div>
              <div className="text-sm text-gray-700">{activeTx.description}</div>
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-100 p-5 mb-5">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-2">
              Reservas seleccionadas ({selectedRes.size})
            </div>
            {selectedRes.size === 0 ? (
              <p className="text-sm text-gray-400">
                Selecciona en la columna derecha las reservas que pertenezcan a este pago.
              </p>
            ) : (
              <div className="space-y-2">
                {Array.from(selectedRes).map((rid) => {
                  const r = reservations.find((x) => x.id === rid);
                  if (!r) return null;
                  return (
                    <div key={rid} className="flex items-center justify-between text-sm">
                      <span>
                        {r.guest_name} <span className="text-gray-400">· {r.channel}</span>
                      </span>
                      <span className="text-gray-600 tabular-nums">{eur(r.gross_amount, r.currency)}</span>
                    </div>
                  );
                })}
                <div className="border-t border-gray-100 mt-2 pt-2 text-sm flex justify-between font-medium">
                  <span>Suma bruto</span>
                  <span className="tabular-nums">{totalReservationsAmount.gross.toFixed(2)} EUR</span>
                </div>
                <div className="text-sm flex justify-between text-gray-600">
                  <span>Suma neto</span>
                  <span className="tabular-nums">{totalReservationsAmount.net.toFixed(2)} EUR</span>
                </div>
                {activeTx && (
                  <DiffBanner
                    bank={activeTx.amount}
                    gross={totalReservationsAmount.gross}
                    net={totalReservationsAmount.net}
                  />
                )}
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => submit('match')}
              disabled={saving || selectedRes.size === 0}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2.5 rounded-lg font-medium flex items-center justify-center gap-2 disabled:opacity-40"
            >
              <Check className="w-4 h-4" /> Match correcto
            </button>
            <button
              onClick={() => submit('no_match')}
              disabled={saving}
              className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-800 px-4 py-2.5 rounded-lg font-medium flex items-center justify-center gap-2"
            >
              <XCircle className="w-4 h-4" /> No es un pago de canal
            </button>
            {labels[activeTx?.id || ''] && (
              <button
                onClick={clearLabel}
                disabled={saving}
                className="px-4 py-2.5 rounded-lg font-medium text-red-600 hover:bg-red-50 border border-red-200"
              >
                Borrar etiqueta
              </button>
            )}
          </div>

          <p className="text-xs text-gray-400 mt-4 leading-relaxed">
            <b>Etiquetado independiente:</b> esta vista no muestra los matches sugeridos
            por la IA — para que tus etiquetas sean ground truth no sesgada. Después
            comparamos las predicciones del sistema contra esto.
          </p>
        </main>

        {/* Right: reservations */}
        <aside className="col-span-4 border-l border-gray-100 bg-white overflow-y-auto flex flex-col">
          <div className="p-3 border-b border-gray-100 sticky top-0 bg-white space-y-2">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-gray-400" />
              <input
                value={resQuery}
                onChange={(e) => setResQuery(e.target.value)}
                placeholder="Buscar reserva (nombre, canal, ID)..."
                className="w-full pl-8 pr-3 py-2 border border-gray-200 rounded-md text-sm"
              />
            </div>
            <div className="flex gap-1 flex-wrap">
              <button
                onClick={() => setChannelFilter('')}
                className={`px-2 py-0.5 rounded text-xs ${
                  channelFilter === '' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700'
                }`}
              >
                Todos
              </button>
              {channels.map((c) => (
                <button
                  key={c}
                  onClick={() => setChannelFilter(c)}
                  className={`px-2 py-0.5 rounded text-xs ${
                    channelFilter === c ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <div>
            {filteredReservations.map((r) => {
              const sel = selectedRes.has(r.id);
              const used = usedElsewhere.has(r.id);
              return (
                <button
                  key={r.id}
                  onClick={() => toggleRes(r.id)}
                  className={`w-full text-left p-3 border-b border-gray-50 text-sm ${
                    sel
                      ? 'bg-emerald-50 hover:bg-emerald-100'
                      : used
                      ? 'bg-amber-50/40 hover:bg-amber-50'
                      : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-gray-900 truncate">
                      {r.guest_name || <i className="text-gray-400">sin nombre</i>}
                    </span>
                    <span className="text-xs text-gray-500">{r.channel}</span>
                  </div>
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>
                      {fmt(r.checkin_date)} → {fmt(r.checkout_date)} · {r.nights ?? '?'}n
                    </span>
                    <span className="tabular-nums">
                      {eur(r.gross_amount, r.currency)} bruto
                    </span>
                  </div>
                  {used && (
                    <div className="mt-1 text-[11px] text-amber-700 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> usada en otro match
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </aside>
      </div>
    </div>
  );
}

function Header({
  progress, labeled, total, matches, noMatches,
}: { progress: number; labeled: number; total: number; matches: number; noMatches: number }) {
  return (
    <header className="bg-white border-b border-gray-100 px-6 py-4 flex items-center gap-6">
      <div className="flex items-center gap-2">
        <ListChecks className="w-5 h-5 text-violet-600" />
        <div>
          <div className="font-semibold text-gray-900">Etiquetado independiente</div>
          <div className="text-xs text-gray-500">Construye el ground truth para evaluar el sistema</div>
        </div>
      </div>
      <div className="flex-1 max-w-md">
        <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
          <span>{labeled} / {total} transacciones etiquetadas</span>
          <span>{progress}%</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-violet-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>
      <div className="flex gap-4 text-sm">
        <span className="text-emerald-700"><b>{matches}</b> match</span>
        <span className="text-gray-500"><b>{noMatches}</b> no es pago</span>
      </div>
    </header>
  );
}

function LabelBadge({ label }: { label?: string }) {
  if (!label) return <span className="text-[10px] text-gray-400">pendiente</span>;
  if (label === 'match') return <span className="text-[10px] text-emerald-700 font-medium">match</span>;
  return <span className="text-[10px] text-gray-500">no es pago</span>;
}

function DiffBanner({ bank, gross, net }: { bank: number; gross: number; net: number }) {
  const diffNet = Math.abs(bank - net);
  const ok = diffNet < 1;
  const close = diffNet < 10;
  return (
    <div
      className={`text-xs mt-2 px-2.5 py-1.5 rounded ${
        ok ? 'bg-emerald-50 text-emerald-800' : close ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-800'
      }`}
    >
      Diferencia banco vs neto: <b>{(bank - net).toFixed(2)} EUR</b>
      {' · '}
      bruto a pagar antes de comisión: <b>{gross.toFixed(2)} EUR</b>
    </div>
  );
}
