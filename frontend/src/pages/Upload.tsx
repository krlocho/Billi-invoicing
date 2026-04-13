import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload as UploadIcon, FileText, FileSpreadsheet, ArrowRight, CheckCircle2, Loader2, Plus, X } from 'lucide-react';
import { uploadBankStatement, uploadChannelFile, createReconciliation, getChannels } from '../services/api';

interface Channel {
  id: string;
  name: string;
  code: string;
}

interface ChannelFileEntry {
  channelId: string;
  file: File | null;
  uploadId: string | null;
  uploading: boolean;
  uploaded: boolean;
}

export default function Upload() {
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [bankUploadId, setBankUploadId] = useState<string | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channelFiles, setChannelFiles] = useState<ChannelFileEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [step, setStep] = useState(1);
  const navigate = useNavigate();
  const bankInputRef = useRef<HTMLInputElement>(null);
  const channelInputRefs = useRef<Record<number, HTMLInputElement | null>>({});

  useEffect(() => {
    getChannels().then((r) => {
      setChannels(r.data);
      // Start with one empty entry
      if (r.data.length > 0) {
        setChannelFiles([{ channelId: r.data[0].id, file: null, uploadId: null, uploading: false, uploaded: false }]);
      }
    }).catch(() => {});
  }, []);

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

  const addChannelEntry = () => {
    // Find first channel not yet used
    const usedIds = channelFiles.map(cf => cf.channelId);
    const available = channels.find(ch => !usedIds.includes(ch.id));
    if (!available) return;
    setChannelFiles([...channelFiles, { channelId: available.id, file: null, uploadId: null, uploading: false, uploaded: false }]);
  };

  const removeChannelEntry = (index: number) => {
    setChannelFiles(channelFiles.filter((_, i) => i !== index));
  };

  const updateChannelEntry = (index: number, updates: Partial<ChannelFileEntry>) => {
    setChannelFiles(channelFiles.map((cf, i) => i === index ? { ...cf, ...updates } : cf));
  };

  const handleChannelUploads = async () => {
    const toUpload = channelFiles.filter(cf => cf.file && !cf.uploaded);
    if (toUpload.length === 0) return;

    for (let i = 0; i < channelFiles.length; i++) {
      const entry = channelFiles[i];
      if (!entry.file || entry.uploaded) continue;

      updateChannelEntry(i, { uploading: true });
      try {
        const res = await uploadChannelFile(entry.file, entry.channelId);
        updateChannelEntry(i, { uploadId: res.data.id, uploaded: true, uploading: false });
      } catch (err) {
        updateChannelEntry(i, { uploading: false });
        alert(`Error al subir ${entry.file.name}`);
        return;
      }
    }
    setStep(3);
  };

  const allChannelFilesReady = channelFiles.length > 0 && channelFiles.every(cf => cf.file !== null);
  const allChannelFilesUploaded = channelFiles.length > 0 && channelFiles.every(cf => cf.uploaded);
  const anyUploading = channelFiles.some(cf => cf.uploading);

  const handleReconcile = async () => {
    if (!bankUploadId) return;
    const uploadIds = channelFiles.map(cf => cf.uploadId).filter(Boolean) as string[];
    if (uploadIds.length === 0) return;
    setReconciling(true);
    try {
      const res = await createReconciliation(bankUploadId, uploadIds);
      navigate(`/app/reconciliation/${res.data.id}`);
    } catch (err) {
      alert('Error al iniciar la conciliacion');
    } finally {
      setReconciling(false);
    }
  };

  const usedChannelIds = channelFiles.map(cf => cf.channelId);
  const canAddMore = channels.filter(ch => !usedChannelIds.includes(ch.id)).length > 0;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Subir ficheros</h1>
        <p className="text-gray-500 mt-1">Sube el extracto bancario y los ficheros de reservas para iniciar la conciliacion</p>
      </div>

      {/* Progress steps */}
      <div className="flex items-center gap-4 mb-10">
        {[
          { num: 1, label: 'Extracto bancario' },
          { num: 2, label: 'Ficheros de canales' },
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

      <div className="max-w-2xl">
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

            <div
              onClick={() => bankInputRef.current?.click()}
              className="block border-2 border-dashed border-gray-200 rounded-xl p-8 text-center hover:border-violet-300 cursor-pointer transition-colors"
            >
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
                ref={bankInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => setBankFile(e.target.files?.[0] || null)}
              />
            </div>

            <button
              onClick={handleBankUpload}
              disabled={!bankFile || uploading}
              className="mt-6 w-full bg-violet-600 hover:bg-violet-700 text-white py-3 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {uploading ? <><Loader2 className="w-4 h-4 animate-spin" /> Subiendo...</> : <>Subir extracto <ArrowRight className="w-4 h-4" /></>}
            </button>
          </div>
        )}

        {/* Step 2: Channel files (multiple) */}
        {step === 2 && (
          <div className="space-y-4">
            {channelFiles.map((entry, index) => (
              <div key={index} className="bg-white rounded-xl border border-gray-100 p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center">
                      {entry.uploaded ? (
                        <CheckCircle2 className="w-5 h-5 text-green-600" />
                      ) : (
                        <FileSpreadsheet className="w-5 h-5 text-blue-600" />
                      )}
                    </div>
                    <select
                      value={entry.channelId}
                      onChange={(e) => updateChannelEntry(index, { channelId: e.target.value })}
                      disabled={entry.uploaded}
                      className="text-sm font-medium text-gray-900 border border-gray-200 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                    >
                      {channels.map(ch => (
                        <option
                          key={ch.id}
                          value={ch.id}
                          disabled={usedChannelIds.includes(ch.id) && ch.id !== entry.channelId}
                        >
                          {ch.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {channelFiles.length > 1 && !entry.uploaded && (
                    <button onClick={() => removeChannelEntry(index)} className="text-gray-400 hover:text-red-500 transition-colors">
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>

                {!entry.uploaded && (
                  <div
                    onClick={() => channelInputRefs.current[index]?.click()}
                    className="block border-2 border-dashed border-gray-200 rounded-xl p-6 text-center hover:border-blue-300 cursor-pointer transition-colors"
                  >
                    <UploadIcon className="w-6 h-6 text-gray-400 mx-auto mb-2" />
                    {entry.file ? (
                      <p className="text-sm font-medium text-gray-900">{entry.file.name}</p>
                    ) : (
                      <>
                        <p className="text-sm text-gray-600">Haz clic para seleccionar CSV/Excel</p>
                        <p className="text-xs text-gray-400 mt-1">CSV, XLSX, XLS</p>
                      </>
                    )}
                    <input
                      ref={(el) => { channelInputRefs.current[index] = el; }}
                      type="file"
                      accept=".csv,.xlsx,.xls"
                      className="hidden"
                      onChange={(e) => updateChannelEntry(index, { file: e.target.files?.[0] || null })}
                    />
                  </div>
                )}

                {entry.uploaded && (
                  <div className="bg-green-50 text-green-700 text-sm p-3 rounded-lg flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    {entry.file?.name} - Subido correctamente
                  </div>
                )}
              </div>
            ))}

            {canAddMore && (
              <button
                onClick={addChannelEntry}
                className="w-full border-2 border-dashed border-gray-200 rounded-xl p-4 text-center hover:border-blue-300 cursor-pointer transition-colors flex items-center justify-center gap-2 text-sm text-gray-500 hover:text-blue-600"
              >
                <Plus className="w-4 h-4" />
                Anadir otro canal
              </button>
            )}

            <button
              onClick={handleChannelUploads}
              disabled={!allChannelFilesReady || anyUploading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {anyUploading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Subiendo...</>
              ) : (
                <>Subir ficheros de canales <ArrowRight className="w-4 h-4" /></>
              )}
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
            <p className="text-gray-500 mb-2">
              1 extracto bancario + {channelFiles.length} {channelFiles.length === 1 ? 'fichero de canal' : 'ficheros de canales'}
            </p>
            <div className="flex flex-wrap justify-center gap-2 mb-8">
              {channelFiles.map((cf, i) => {
                const ch = channels.find(c => c.id === cf.channelId);
                return (
                  <span key={i} className="bg-blue-50 text-blue-700 text-xs font-medium px-3 py-1 rounded-full">
                    {ch?.name || 'Canal'}
                  </span>
                );
              })}
            </div>

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
