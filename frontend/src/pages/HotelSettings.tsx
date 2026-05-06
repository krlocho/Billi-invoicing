import { useEffect, useState } from 'react';
import { Building2, Save, CheckCircle2 } from 'lucide-react';
import { getMyTenant, updateMyTenant } from '../services/api';

const TAX_PRESETS: Record<string, { type: string; rate: number; region?: string }> = {
  canarias: { type: 'IGIC', rate: 7, region: 'Canarias' },
  ceuta_melilla: { type: 'IPSI', rate: 4, region: 'Ceuta/Melilla' },
  peninsula_reducido: { type: 'IVA', rate: 10, region: 'Península (reducido)' },
  peninsula_general: { type: 'IVA', rate: 21, region: 'Península (general)' },
};

interface Form {
  name: string;
  tax_id: string;
  address: string;
  tax_type: string;
  tax_rate: number;
  country: string;
  region: string;
}

export default function HotelSettings() {
  const [form, setForm] = useState<Form | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMyTenant()
      .then((r) => {
        const t = r.data;
        setForm({
          name: t.name || '',
          tax_id: t.tax_id || '',
          address: t.address || '',
          tax_type: t.settings?.tax_type || 'IVA',
          tax_rate: Number(t.settings?.tax_rate ?? 10),
          country: t.settings?.country || 'ES',
          region: t.settings?.region || '',
        });
      })
      .catch((e) => setError(e?.response?.data?.detail || 'Error cargando datos'));
  }, []);

  if (!form) {
    return <div className="text-gray-500">Cargando configuración...</div>;
  }

  const update = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  const applyPreset = (key: string) => {
    const p = TAX_PRESETS[key];
    if (!p) return;
    update({ tax_type: p.type, tax_rate: p.rate, region: p.region || '' });
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateMyTenant({
        name: form.name,
        tax_id: form.tax_id,
        address: form.address,
        settings: {
          tax_type: form.tax_type,
          tax_rate: Number(form.tax_rate),
          country: form.country || null,
          region: form.region || null,
        },
      });
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 3000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Error guardando');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 bg-violet-50 rounded-lg flex items-center justify-center">
          <Building2 className="w-5 h-5 text-violet-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Configuración del hotel</h1>
          <p className="text-gray-500 text-sm">Datos fiscales que aparecen en las facturas generadas</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-800 text-sm rounded-lg px-4 py-2.5">
          {error}
        </div>
      )}

      <form onSubmit={submit} className="space-y-6">
        <Section title="Datos legales">
          <Field label="Razón social">
            <input
              className="input"
              value={form.name}
              onChange={(e) => update({ name: e.target.value })}
              required
            />
          </Field>
          <Field label="CIF / NIF">
            <input
              className="input"
              value={form.tax_id}
              placeholder="B12345678"
              onChange={(e) => update({ tax_id: e.target.value })}
            />
          </Field>
          <Field label="Dirección fiscal">
            <input
              className="input"
              value={form.address}
              placeholder="Calle, número, ciudad, CP"
              onChange={(e) => update({ address: e.target.value })}
            />
          </Field>
        </Section>

        <Section title="Impuesto" subtitle="Selecciona un preset o introduce el tuyo">
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(TAX_PRESETS).map(([key, p]) => (
              <button
                type="button"
                key={key}
                onClick={() => applyPreset(key)}
                className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                  form.tax_type === p.type && form.tax_rate === p.rate
                    ? 'bg-violet-600 text-white border-violet-600'
                    : 'bg-white text-gray-700 border-gray-200 hover:border-violet-300'
                }`}
              >
                {p.type} {p.rate}% · {p.region}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Tipo (IVA, IGIC, VAT, ...)">
              <input
                className="input"
                value={form.tax_type}
                onChange={(e) => update({ tax_type: e.target.value.toUpperCase() })}
                required
              />
            </Field>
            <Field label="Tasa (%)">
              <input
                className="input"
                type="number"
                step="0.01"
                value={form.tax_rate}
                onChange={(e) => update({ tax_rate: Number(e.target.value) })}
                required
              />
            </Field>
            <Field label="País (ISO)">
              <input
                className="input"
                value={form.country}
                onChange={(e) => update({ country: e.target.value.toUpperCase() })}
                maxLength={2}
              />
            </Field>
            <Field label="Región">
              <input
                className="input"
                value={form.region}
                onChange={(e) => update({ region: e.target.value })}
              />
            </Field>
          </div>
        </Section>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="bg-violet-600 hover:bg-violet-700 text-white px-5 py-2.5 rounded-lg font-medium flex items-center gap-2 disabled:opacity-60"
          >
            <Save className="w-4 h-4" /> {saving ? 'Guardando...' : 'Guardar cambios'}
          </button>
          {savedAt && (
            <span className="text-emerald-700 text-sm flex items-center gap-1">
              <CheckCircle2 className="w-4 h-4" /> Guardado
            </span>
          )}
        </div>
      </form>

      <style>{`.input { width: 100%; padding: 0.55rem 0.75rem; border: 1px solid #e5e7eb; border-radius: 0.5rem; font-size: 0.875rem; }
        .input:focus { outline: none; border-color: #8b5cf6; box-shadow: 0 0 0 3px rgba(139,92,246,0.2); }`}</style>
    </div>
  );
}

function Section({
  title, subtitle, children,
}: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-6">
      <h2 className="font-semibold text-gray-900 mb-1">{title}</h2>
      {subtitle && <p className="text-xs text-gray-500 mb-4">{subtitle}</p>}
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>
      {children}
    </label>
  );
}
