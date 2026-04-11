import { Link } from 'react-router-dom';
import {
  FileText, Brain, Zap, Shield, ArrowRight, CheckCircle2,
  Upload, GitCompare, Receipt, BarChart3, Building2, Plug
} from 'lucide-react';

export default function Landing() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navbar */}
      <nav className="fixed top-0 w-full bg-white/80 backdrop-blur-md border-b border-gray-100 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-violet-600 rounded-lg flex items-center justify-center">
              <FileText className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-gray-900">Billi</span>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm text-gray-600">
            <a href="#features" className="hover:text-gray-900 transition-colors">Funcionalidades</a>
            <a href="#how-it-works" className="hover:text-gray-900 transition-colors">Como funciona</a>
            <a href="#pricing" className="hover:text-gray-900 transition-colors">Planes</a>
            <a href="#api" className="hover:text-gray-900 transition-colors">API para PMS</a>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm text-gray-600 hover:text-gray-900 px-4 py-2">
              Iniciar sesion
            </Link>
            <Link
              to="/register"
              className="text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 px-5 py-2.5 rounded-lg transition-colors"
            >
              Prueba gratis
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-violet-50 text-violet-700 px-4 py-1.5 rounded-full text-sm font-medium mb-6">
            <Brain className="w-4 h-4" />
            Potenciado por Inteligencia Artificial
          </div>
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 leading-tight mb-6">
            Facturacion hotelera{' '}
            <span className="text-violet-600">automatica</span>{' '}
            e inteligente
          </h1>
          <p className="text-xl text-gray-600 mb-10 max-w-2xl mx-auto">
            Billi concilia automaticamente los pagos de Booking, Expedia y otros canales
            con tus reservas y genera las facturas al instante. Sin errores. Sin horas perdidas.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/register"
              className="flex items-center gap-2 bg-violet-600 hover:bg-violet-700 text-white px-8 py-4 rounded-xl text-lg font-medium transition-colors"
            >
              Empieza gratis <ArrowRight className="w-5 h-5" />
            </Link>
            <a
              href="#how-it-works"
              className="flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-8 py-4 rounded-xl text-lg font-medium transition-colors"
            >
              Ver como funciona
            </a>
          </div>
          <div className="mt-12 flex items-center justify-center gap-8 text-sm text-gray-500">
            <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-green-500" /> Sin tarjeta de credito</div>
            <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-green-500" /> Setup en 5 minutos</div>
            <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-green-500" /> API para PMS</div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-16 bg-gray-50 border-y border-gray-100">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {[
            { value: '95%', label: 'Precision en matching' },
            { value: '2-4h', label: 'Ahorradas por dia' },
            { value: '<30s', label: 'Tiempo de proceso' },
            { value: '0', label: 'Errores humanos' },
          ].map((stat) => (
            <div key={stat.label}>
              <div className="text-3xl font-bold text-violet-600">{stat.value}</div>
              <div className="text-sm text-gray-600 mt-1">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Todo lo que necesitas para automatizar tu facturacion</h2>
            <p className="text-gray-600 max-w-2xl mx-auto">Desde la extraccion del extracto bancario hasta la factura generada, Billi se encarga de todo.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: Brain,
                title: 'IA que entiende tus datos',
                desc: 'Nuestro motor de IA interpreta extractos bancarios, identifica canales y empareja pagos agrupados con reservas automaticamente.',
              },
              {
                icon: GitCompare,
                title: 'Conciliacion inteligente',
                desc: 'Maneja pagos agrupados de Booking, Expedia, Hotelbeds... Calcula comisiones y resuelve discrepancias de nombres.',
              },
              {
                icon: Receipt,
                title: 'Facturas automaticas',
                desc: 'Genera facturas PDF profesionales con los datos de cada reserva, IVA incluido, listas para enviar al huesped.',
              },
              {
                icon: Shield,
                title: 'Validacion hibrida',
                desc: 'La IA propone, los algoritmos validan. Cada match se verifica con subset-sum, fuzzy matching y reglas de comision.',
              },
              {
                icon: Zap,
                title: 'Aprende contigo',
                desc: 'Cada correccion que haces mejora el sistema. Few-shot learning adapta las predicciones a tu hotel.',
              },
              {
                icon: BarChart3,
                title: 'Dashboard y metricas',
                desc: 'Visualiza el estado de tus conciliaciones, facturas pendientes y el porcentaje de automatizacion.',
              },
            ].map((f) => (
              <div key={f.title} className="bg-white border border-gray-100 rounded-2xl p-6 hover:shadow-lg transition-shadow">
                <div className="w-12 h-12 bg-violet-50 rounded-xl flex items-center justify-center mb-4">
                  <f.icon className="w-6 h-6 text-violet-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-gray-600 text-sm">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-20 px-6 bg-gray-50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Como funciona</h2>
            <p className="text-gray-600">4 pasos simples para automatizar tu facturacion</p>
          </div>
          <div className="grid md:grid-cols-4 gap-6">
            {[
              { step: '1', icon: Upload, title: 'Sube tus ficheros', desc: 'Extracto bancario (PDF) y fichero de reservas del canal (CSV).' },
              { step: '2', icon: Brain, title: 'La IA analiza', desc: 'Extrae transacciones, identifica canales y calcula comisiones.' },
              { step: '3', icon: GitCompare, title: 'Conciliacion', desc: 'Empareja cada pago con sus reservas. Revisa solo los casos dudosos.' },
              { step: '4', icon: Receipt, title: 'Facturas listas', desc: 'Genera y descarga las facturas PDF de cada reserva.' },
            ].map((s) => (
              <div key={s.step} className="text-center">
                <div className="w-14 h-14 bg-violet-600 rounded-2xl flex items-center justify-center mx-auto mb-4 text-white font-bold text-xl">
                  {s.step}
                </div>
                <h3 className="font-semibold text-gray-900 mb-2">{s.title}</h3>
                <p className="text-sm text-gray-600">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* API for PMS */}
      <section id="api" className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-3 py-1 rounded-full text-sm font-medium mb-4">
                <Plug className="w-4 h-4" /> API REST
              </div>
              <h2 className="text-3xl font-bold text-gray-900 mb-4">Integra Billi en tu PMS</h2>
              <p className="text-gray-600 mb-6">
                Nuestra API REST permite a cualquier PMS (Property Management System) integrar la conciliacion
                y facturacion automatica directamente en su plataforma.
              </p>
              <ul className="space-y-3">
                {[
                  'Sincroniza reservas via API',
                  'Lanza conciliaciones programadas',
                  'Recibe resultados via webhooks',
                  'Descarga facturas generadas',
                  'Documentacion OpenAPI/Swagger completa',
                ].map((item) => (
                  <li key={item} className="flex items-center gap-3 text-sm text-gray-700">
                    <CheckCircle2 className="w-5 h-5 text-green-500 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-gray-900 rounded-2xl p-6 text-left">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                <div className="w-3 h-3 rounded-full bg-green-500"></div>
                <span className="text-gray-500 text-xs ml-2">API Request</span>
              </div>
              <pre className="text-sm text-gray-300 overflow-x-auto">
{`POST /api/v1/reconciliations
Authorization: Bearer <token>
Content-Type: application/json

{
  "bank_upload_id": "uuid-...",
  "channel_upload_ids": [
    "uuid-booking-...",
    "uuid-expedia-..."
  ]
}

// Response
{
  "id": "rec-uuid-...",
  "status": "running",
  "matched_auto": 0,
  "matched_manual": 0,
  "unmatched": 0
}`}
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 px-6 bg-gray-50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">Planes simples, sin sorpresas</h2>
            <p className="text-gray-600">Elige el plan que mejor se adapte a tu hotel</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                name: 'Starter',
                price: '49',
                desc: 'Para hoteles pequenos',
                features: ['Hasta 200 facturas/mes', '1 canal de reservas', 'OCR de extractos', 'Soporte email'],
                cta: 'Empieza gratis',
                featured: false,
              },
              {
                name: 'Professional',
                price: '99',
                desc: 'Para hoteles medianos',
                features: ['Facturas ilimitadas', 'Todos los canales', 'IA avanzada + few-shot', 'API acceso', 'Soporte prioritario'],
                cta: 'Prueba 14 dias gratis',
                featured: true,
              },
              {
                name: 'Enterprise',
                price: 'Custom',
                desc: 'Para cadenas y PMS',
                features: ['Multi-hotel', 'API completa + webhooks', 'SLA garantizado', 'Integracion dedicada', 'Account manager'],
                cta: 'Contactar',
                featured: false,
              },
            ].map((plan) => (
              <div
                key={plan.name}
                className={`rounded-2xl p-8 ${
                  plan.featured
                    ? 'bg-violet-600 text-white ring-4 ring-violet-200 scale-105'
                    : 'bg-white border border-gray-200'
                }`}
              >
                <h3 className={`text-lg font-semibold ${plan.featured ? 'text-white' : 'text-gray-900'}`}>{plan.name}</h3>
                <p className={`text-sm mt-1 ${plan.featured ? 'text-violet-200' : 'text-gray-500'}`}>{plan.desc}</p>
                <div className="mt-6 mb-8">
                  <span className={`text-4xl font-bold ${plan.featured ? 'text-white' : 'text-gray-900'}`}>
                    {plan.price === 'Custom' ? '' : '€'}{plan.price}
                  </span>
                  {plan.price !== 'Custom' && <span className={`text-sm ${plan.featured ? 'text-violet-200' : 'text-gray-500'}`}>/mes</span>}
                </div>
                <ul className="space-y-3 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className={`flex items-center gap-2 text-sm ${plan.featured ? 'text-violet-100' : 'text-gray-600'}`}>
                      <CheckCircle2 className={`w-4 h-4 shrink-0 ${plan.featured ? 'text-violet-300' : 'text-green-500'}`} />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/register"
                  className={`block text-center py-3 rounded-lg font-medium text-sm transition-colors ${
                    plan.featured
                      ? 'bg-white text-violet-600 hover:bg-violet-50'
                      : 'bg-violet-600 text-white hover:bg-violet-700'
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <Building2 className="w-12 h-12 text-violet-600 mx-auto mb-6" />
          <h2 className="text-3xl font-bold text-gray-900 mb-4">Deja de perder horas con la facturacion</h2>
          <p className="text-gray-600 mb-8">
            Unete a los hoteles que ya automatizan su conciliacion bancaria y generacion de facturas con IA.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 bg-violet-600 hover:bg-violet-700 text-white px-8 py-4 rounded-xl text-lg font-medium transition-colors"
          >
            Empieza ahora <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-100 py-12 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-violet-600 rounded flex items-center justify-center">
              <FileText className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900">Billi</span>
            <span className="text-gray-400 text-sm ml-2">&copy; 2026</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-gray-500">
            <a href="#" className="hover:text-gray-900">Privacidad</a>
            <a href="#" className="hover:text-gray-900">Terminos</a>
            <a href="#" className="hover:text-gray-900">Contacto</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
