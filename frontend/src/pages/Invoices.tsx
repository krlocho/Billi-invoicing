import { useEffect, useState } from 'react';
import { Receipt, Download, FileText } from 'lucide-react';
import { getInvoices, getInvoicePdf } from '../services/api';

export default function Invoices() {
  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInvoices()
      .then((r) => setInvoices(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Facturas</h1>
        <p className="text-gray-500 mt-1">Todas las facturas generadas automaticamente</p>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">Cargando facturas...</div>
      ) : invoices.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
          <Receipt className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No hay facturas todavia</h3>
          <p className="text-gray-500 text-sm">Las facturas se generaran automaticamente al confirmar las conciliaciones</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">N Factura</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Huesped</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Fecha</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Check-in</th>
                <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 uppercase">Check-out</th>
                <th className="text-right px-6 py-3 text-xs font-medium text-gray-500 uppercase">Total</th>
                <th className="text-center px-6 py-3 text-xs font-medium text-gray-500 uppercase">Estado</th>
                <th className="px-6 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {invoices.map((inv: any) => (
                <tr key={inv.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-violet-600" />
                      <span className="text-sm font-medium text-gray-900">{inv.invoice_number}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">{inv.guest_name || 'N/A'}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{inv.issue_date}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{inv.checkin_date || '-'}</td>
                  <td className="px-6 py-4 text-sm text-gray-500">{inv.checkout_date || '-'}</td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900 text-right">
                    {inv.total?.toFixed(2)} {inv.currency}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      inv.status === 'issued' ? 'bg-green-50 text-green-700' :
                      inv.status === 'sent' ? 'bg-blue-50 text-blue-700' :
                      'bg-gray-50 text-gray-700'
                    }`}>
                      {inv.status === 'issued' ? 'Emitida' : inv.status === 'sent' ? 'Enviada' : inv.status}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <a
                      href={getInvoicePdf(inv.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-sm text-violet-600 hover:text-violet-700 font-medium"
                    >
                      <Download className="w-4 h-4" /> PDF
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
