import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Upload, GitCompare, Receipt, ArrowRight, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import { getUploads, getInvoices } from '../services/api';

export default function Dashboard() {
  const [uploads, setUploads] = useState<any[]>([]);
  const [invoices, setInvoices] = useState<any[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    getUploads().then((r) => setUploads(r.data)).catch(() => {});
    getInvoices().then((r) => setInvoices(r.data)).catch(() => {});
  }, []);

  const bankStatements = uploads.filter((u) => u.file_type === 'bank_statement');
  const channelFiles = uploads.filter((u) => u.file_type === 'channel_file');

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Resumen de tu actividad de facturacion</p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Extractos subidos', value: bankStatements.length, icon: Upload, color: 'violet' },
          { label: 'Ficheros de canales', value: channelFiles.length, icon: GitCompare, color: 'blue' },
          { label: 'Facturas generadas', value: invoices.length, icon: Receipt, color: 'green' },
          { label: 'Pendientes de revision', value: 0, icon: AlertCircle, color: 'amber' },
        ].map((stat) => (
          <div key={stat.label} className="bg-white rounded-xl border border-gray-100 p-5">
            <div className="flex items-center justify-between mb-3">
              <stat.icon className={`w-5 h-5 text-${stat.color}-600`} />
            </div>
            <div className="text-2xl font-bold text-gray-900">{stat.value}</div>
            <div className="text-sm text-gray-500">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <button
          onClick={() => navigate('/app/upload')}
          className="bg-violet-50 hover:bg-violet-100 border border-violet-100 rounded-xl p-6 text-left transition-colors group"
        >
          <Upload className="w-8 h-8 text-violet-600 mb-3" />
          <h3 className="text-lg font-semibold text-gray-900 mb-1">Subir ficheros</h3>
          <p className="text-sm text-gray-600 mb-3">Sube un extracto bancario y ficheros de reservas para iniciar la conciliacion</p>
          <span className="flex items-center gap-1 text-sm font-medium text-violet-600 group-hover:gap-2 transition-all">
            Empezar <ArrowRight className="w-4 h-4" />
          </span>
        </button>
        <button
          onClick={() => navigate('/app/invoices')}
          className="bg-green-50 hover:bg-green-100 border border-green-100 rounded-xl p-6 text-left transition-colors group"
        >
          <Receipt className="w-8 h-8 text-green-600 mb-3" />
          <h3 className="text-lg font-semibold text-gray-900 mb-1">Ver facturas</h3>
          <p className="text-sm text-gray-600 mb-3">Consulta y descarga las facturas generadas automaticamente</p>
          <span className="flex items-center gap-1 text-sm font-medium text-green-600 group-hover:gap-2 transition-all">
            Ver facturas <ArrowRight className="w-4 h-4" />
          </span>
        </button>
      </div>

      {/* Recent uploads */}
      {uploads.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100">
          <div className="px-6 py-4 border-b border-gray-50">
            <h2 className="font-semibold text-gray-900">Ficheros recientes</h2>
          </div>
          <div className="divide-y divide-gray-50">
            {uploads.slice(0, 5).map((u: any) => (
              <div key={u.id} className="px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {u.status === 'completed' ? (
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                  ) : u.status === 'failed' ? (
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  ) : (
                    <Clock className="w-5 h-5 text-amber-500" />
                  )}
                  <div>
                    <div className="text-sm font-medium text-gray-900">{u.original_filename}</div>
                    <div className="text-xs text-gray-500">{u.file_type === 'bank_statement' ? 'Extracto bancario' : 'Fichero de canal'}</div>
                  </div>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                  u.status === 'completed' ? 'bg-green-50 text-green-700' :
                  u.status === 'failed' ? 'bg-red-50 text-red-700' :
                  'bg-amber-50 text-amber-700'
                }`}>
                  {u.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
