import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Reconciliation from './pages/Reconciliation';
import Invoices from './pages/Invoices';
import HotelSettings from './pages/HotelSettings';
import Labeling from './pages/Labeling';
import AppLayout from './components/AppLayout';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected - App */}
        <Route path="/app" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="upload" element={<Upload />} />
          <Route path="reconciliation/:id" element={<Reconciliation />} />
          <Route path="invoices" element={<Invoices />} />
          <Route path="settings" element={<HotelSettings />} />
          <Route path="labeling/:id" element={<Labeling />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
