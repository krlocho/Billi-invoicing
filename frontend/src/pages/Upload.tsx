import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload as UploadIcon, FileText, FileSpreadsheet, ArrowRight, CheckCircle2, Loader2 } from 'lucide-react';
import { uploadBankStatement, uploadChannelFile, createReconciliation } from '../services/api';

export default function Upload() {
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [channelFile, setChannelFile] = useState<File | null>(null);
  const [bankUploadId, setBankUploadId] = useState<string | null>(null);
  const [channelUploadId, setChannelUploadId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [step, setStep] = useState(1);
  const navigate = useNavigate();

  const handleBankUpload = async () => {
    if (!bankFile) return;
    setUploading(true);
    try {
      const res = await uploadBankStatement(bankFile);
      setBankUploadId(res.data.id);
      setStep(2);
    } catch (err) {
      alert('Error al subir el extracto bancario');
    } finally {
      setUploading(false);
    }
  };

  const handleChannelUpload = async () => {
    if (!channelFile) return;
    setUploading(true);
    try {
      // Using a placeholder channel ID - in production this would be selected
      const res = await uploadChannelFile(channelFile, '00000000-0000-0000-0000-000000000001');
      setChannelUploadId(res.data.id);
      setStep(3);
    } catch (err) {
      alert('Error al subir el fichero de reservas');
    } finally {
      setUploading(false);
    }
  };

  const handleReconcile = async () => {
    if (!bankUploadId || !channelUploadId) return;
    setReconciling(true);
    try {
      const res = await createReconciliation(bankUploadId, [channelUploadId]);
      navigate(`/app/reconciliation/${res.data.id}`);
    } catch (err) {
      alert('Error al iniciar la conciliacion');
    } finally {
      setReconciling(false);
    }
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Subir ficheros</h1>
        <p className="text-gray-500 mt-1">Sube el extracto bancario y el fichero de reservas para iniciar la conciliacion</p>
      </div>

      {/* Progress steps */}
      <div className="flex items-center gap-4 mb-10">
        {[
          { num: 1, label: 'Extracto bancario' },
          { num: 2, label: 'Fichero de reservas' },
          { num: 3, label: 'Conciliar' },
        ].map((s) => (
          <div key={s.num} className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
              step >= s.num ? 'bg-violet-600 text-white' : 'bg-gray-100 text-gray-400'
            }`}>
              {step > s.num ? <CheckCircle2 className="w-5 h-5" /> : s.num}
            </div>
            <span className={`text-sm ${step >= s.num ? 'text-gray-900 font-medium' : 'text-gray-400'}`}>
              {s.label}
            </span>
            {s.num < 3 && <ArrowRight className="w-4 h-4 text-gray-300 ml-2" />}
          </div>
        ))}
      </div>

      <div className="max-w-xl">
        {/* Step 1: Bank statement */}
        {step === 1 && (
          <div className="bg-white rounded-xl border border-gray-100 p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 bg-violet-50 rounded-xl flex items-center justify-center">
                <FileText className="w-6 h-6 text-violet-600" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-900">Extracto bancario</h2>
                <p className="text-sm text-gray-500">Sube el PDF del extracto de tu banco</p>
              </div>
            </div>

            <label className="block border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-violet-300 cursor-pointer transition-colors">
              <UploadIcon className="w-8 h-8 text-gray-400 mx-auto mb-3" />
              {bankFile ? (
                <p className="text-sm font-medium text-gray-900">{bankFile.name}</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600">Arrastra tu PDF aqui o haz clic para seleccionar</p>
                  <p className="text-xs text-gray-400 mt-1">Solo ficheros PDF</p>
                </>
              )}
              <input
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => setBankFile(e.target.files?.[0] || null)}
              />
            </label>

            <button
              onClick={handleBankUpload}
              disabled={!bankFile || uploading}
              className="mt-6 w-full bg-violet-600 hover:bg-violet-700 text-white py-3 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Subiendo...</> : <>Subir extracto <ArrowRight className="w-4 h-4" /></>}
            </button>
          </div>
        )}

        {/* Step 2: Channel file */}
        {step === 2 && (
          <div className="bg-white rounded-xl border border-gray-100 p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center">
                <FileSpreadsheet className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h2 className="font-semibold text-gray-900">Fichero de reservas</h2>
                <p className="text-sm text-gray-500">Sube el CSV/Excel exportado del canal (Booking, Expedia...)</p>
              </div>
            </div>

            <label className="block border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-blue-300 cursor-pointer transition-colors">
              <UploadIcon className="w-8 h-8 text-gray-400 mx-auto mb-3" />
              {channelFile ? (
                <p className="text-sm font-medium text-gray-900">{channelFile.name}</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600">Arrastra tu CSV/Excel aqui o haz clic para seleccionar</p>
                  <p className="text-xs text-gray-400 mt-1">CSV, XLSX, XLS</p>
                </>
              )}
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => setChannelFile(e.target.files?.[0] || null)}
              />
            </label>

            <button
              onClick={handleChannelUpload}
              disabled={!channelFile || uploading}
              className="mt-6 w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Subiendo...</> : <>Subir reservas <ArrowRight className="w-4 h-4" /></>}
            </button>
          </div>
        )}

        {/* Step 3: Reconcile */}
        {step === 3 && (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center">
            <div className="w-16 h-16 bg-green-50 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <CheckCircle2 className="w-8 h-8 text-green-600" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Ficheros subidos correctamente</h2>
            <p className="text-gray-500 mb-8">Todo listo para iniciar la conciliacion con IA</p>

            <button
              onClick={handleReconcile}
              disabled={reconciling}
              className="bg-violet-600 hover:bg-violet-700 text-white px-8 py-3 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center gap-2 mx-auto"
            >
              {reconciling ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Conciliando...</>
              ) : (
                <>Iniciar conciliacion con IA <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
