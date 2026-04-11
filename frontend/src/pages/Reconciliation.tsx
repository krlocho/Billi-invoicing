import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { CheckCircle2, XCircle, Clock, Brain, ArrowRight, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { getReconciliation, getMatches, updateMatch, confirmAllHigh, generateInvoices } from '../services/api';

export default function Reconciliation() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rec, setRec] = useState<any>(null);
  const [matches, setMatches] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedMatch, setExpandedMatch] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    if (!id) return;
    const poll = setInterval(async () => {
      try {
        const recRes = await getReconciliation(id);
        setRec(recRes.data);
        if (recRes.data.status === 'completed' || recRes.data.status === 'failed') {
          setPolling(false);
          clearInterval(poll);
          const matchRes = await getMatches(id);
          setMatches(matchRes.data);
        }
        setLoading(false);
      } catch {
        clearInterval(poll);
        setLoading(false);
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [id]);

  const handleConfirmAll = async () => {
    if (!id) return;
    await confirmAllHigh(id);
    const matchRes = await getMatches(id);
    setMatches(matchRes.data);
  };

  const handleMatchAction = async (matchId: string, status: string) => {
    if (!id) return;
    await updateMatch(id, matchId, { status });
    const matchRes = await getMatches(id);
    setMatches(matchRes.data);
  };

  const handleGenerateInvoices = async () => {
    if (!id) return;
    await generateInvoices(id);
    navigate('/app/invoices');
  };

  const tierColor = (tier: string) => {
    switch (tier) {
      case 'HIGH': return 'bg-green-50 text-green-700 border-green-200';
      case 'MEDIUM': return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'LOW': return 'bg-red-50 text-red-700 border-red-200';
      default: return 'bg-gray-50 text-gray-700 border-gray-200';
    }
  };

  const tierLabel = (tier: string) => {
    switch (tier) {
      case 'HIGH': return 'Alta confianza';
      case 'MEDIUM': return 'Media confianza';
      case 'LOW': return 'Baja confianza';
      default: return tier;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Loader2 className="w-10 h-10 text-violet-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Cargando conciliacion...</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Resultados de conciliacion</h1>
        <p className="text-gray-500 mt-1">Revisa los matches generados por la IA</p>
      </div>

      {/* Status */}
      {rec && (
        <div className="bg-white rounded-xl border border-gray-100 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              {rec.status === 'running' ? (
                <Loader2 className="w-6 h-6 text-violet-600 animate-spin" />
              ) : rec.status === 'completed' ? (
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              ) : (
                <XCircle className="w-6 h-6 text-red-600" />
              )}
              <span className="font-semibold text-gray-900">
                {rec.status === 'running' ? 'La IA esta analizando tus datos...' :
                 rec.status === 'completed' ? 'Conciliacion completada' : 'Error en la conciliacion'}
              </span>
            </div>
            {rec.status === 'completed' && (
              <div className="flex gap-3">
                <button
                  onClick={handleConfirmAll}
                  className="text-sm bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  Confirmar alta confianza
                </button>
                <button
                  onClick={handleGenerateInvoices}
                  className="text-sm bg-violet-600 hover:bg-violet-700 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                >
                  Generar facturas <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {rec.status === 'completed' && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-gray-900">{rec.total_transactions}</div>
                <div className="text-xs text-gray-500">Transacciones</div>
              </div>
              <div className="bg-green-50 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-green-700">{rec.matched_auto}</div>
                <div className="text-xs text-green-600">Auto-match</div>
              </div>
              <div className="bg-amber-50 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-amber-700">{rec.matched_manual}</div>
                <div className="text-xs text-amber-600">Requieren revision</div>
              </div>
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-red-700">{rec.unmatched}</div>
                <div className="text-xs text-red-600">Sin match</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Matches */}
      {matches.length > 0 && (
        <div className="space-y-3">
          {matches.map((match: any) => (
            <div key={match.id} className="bg-white rounded-xl border border-gray-100 overflow-hidden">
              <div
                className="px-6 py-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
                onClick={() => setExpandedMatch(expandedMatch === match.id ? null : match.id)}
              >
                <div className="flex items-center gap-4">
                  <Brain className="w-5 h-5 text-violet-600" />
                  <div>
                    <div className="text-sm font-medium text-gray-900">
                      Match #{match.id.substring(0, 8)} — {match.reservation_ids.length} reserva(s)
                    </div>
                    <div className="text-xs text-gray-500">
                      Confianza: {match.confidence_score ? (match.confidence_score * 100).toFixed(1) : 0}%
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium border ${tierColor(match.confidence_tier)}`}>
                    {tierLabel(match.confidence_tier)}
                  </span>
                  {match.status === 'confirmed' ? (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  ) : match.status === 'rejected' ? (
                    <XCircle className="w-5 h-5 text-red-500" />
                  ) : (
                    <Clock className="w-5 h-5 text-amber-500" />
                  )}
                  {expandedMatch === match.id ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </div>
              </div>

              {expandedMatch === match.id && (
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-100">
                  {match.match_details?.reasoning && (
                    <div className="mb-4 p-3 bg-violet-50 rounded-lg">
                      <div className="text-xs font-medium text-violet-700 mb-1 flex items-center gap-1">
                        <Brain className="w-3 h-3" /> Razonamiento de la IA
                      </div>
                      <p className="text-sm text-violet-900">{match.match_details.reasoning}</p>
                    </div>
                  )}

                  {match.amount_difference !== null && (
                    <div className="text-sm text-gray-600 mb-4">
                      Diferencia de importe: <span className="font-medium">{match.amount_difference?.toFixed(2)} EUR</span>
                    </div>
                  )}

                  {match.status === 'pending' && (
                    <div className="flex gap-3">
                      <button
                        onClick={() => handleMatchAction(match.id, 'confirmed')}
                        className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Confirmar
                      </button>
                      <button
                        onClick={() => handleMatchAction(match.id, 'rejected')}
                        className="flex items-center gap-2 bg-red-100 hover:bg-red-200 text-red-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                      >
                        <XCircle className="w-4 h-4" /> Rechazar
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
