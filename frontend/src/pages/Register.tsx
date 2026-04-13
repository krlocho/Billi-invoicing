import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FileText } from 'lucide-react';
import { register } from '../services/api';

export default function Register() {
  const [form, setForm] = useState({ email: '', password: '', full_name: '', tenant_name: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await register(form);
      const token = res.data.access_token;
      if (!token) {
        setError('No se recibio token del servidor');
        return;
      }
      localStorage.setItem('token', token);
      window.location.href = '/app';
    } catch (err: any) {
      console.error('Register error:', err);
      setError(err?.response?.data?.detail || 'Error al registrar. El email podria estar en uso.');
    } finally {
      setLoading(false);
    }
  };

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: e.target.value });

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 mb-6">
            <div className="w-10 h-10 bg-violet-600 rounded-xl flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <span className="text-2xl font-bold text-gray-900">Billi</span>
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Crear cuenta</h1>
          <p className="text-gray-500 mt-2">Empieza a automatizar tu facturacion</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 space-y-5">
          {error && <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg">{error}</div>}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Nombre del hotel</label>
            <input
              type="text"
              value={form.tenant_name}
              onChange={update('tenant_name')}
              placeholder="Hotel Sol y Mar"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Tu nombre</label>
            <input
              type="text"
              value={form.full_name}
              onChange={update('full_name')}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={update('email')}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Contrasena</label>
            <input
              type="password"
              value={form.password}
              onChange={update('password')}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none"
              required
              minLength={6}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-violet-600 hover:bg-violet-700 text-white py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Creando cuenta...' : 'Crear cuenta'}
          </button>
          <p className="text-center text-sm text-gray-500">
            Ya tienes cuenta?{' '}
            <Link to="/login" className="text-violet-600 hover:underline font-medium">Inicia sesion</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
