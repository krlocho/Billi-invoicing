import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Only redirect to login if we're NOT already on the login/register page
      // and NOT in the middle of a login/register request
      const url = error.config?.url || '';
      const isAuthRequest = url.includes('/auth/login') || url.includes('/auth/register');
      if (!isAuthRequest) {
        localStorage.removeItem('token');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Auth
export const login = (email: string, password: string) =>
  api.post('/auth/login', { email, password });

export const register = (data: { email: string; password: string; full_name: string; tenant_name: string }) =>
  api.post('/auth/register', data);

// Tenant (hotel) settings
export const getMyTenant = () => api.get('/tenants/me');
export const updateMyTenant = (data: {
  name?: string;
  tax_id?: string;
  address?: string;
  settings?: { tax_type: string; tax_rate: number; country?: string | null; region?: string | null };
}) => api.put('/tenants/me', data);

// Channels
export const getChannels = () => api.get('/channels/');

// Uploads
export const uploadBankStatement = (file: File) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/uploads/bank-statement', form);
};

export const uploadChannelFile = (file: File, channelId: string) => {
  const form = new FormData();
  form.append('file', file);
  form.append('channel_id', channelId);
  return api.post('/uploads/channel-file', form);
};

export const getUploads = () => api.get('/uploads/');
export const getUpload = (id: string) => api.get(`/uploads/${id}`);

// Reconciliations
export const createReconciliation = (bankUploadId: string, channelUploadIds: string[]) =>
  api.post('/reconciliations/', { bank_upload_id: bankUploadId, channel_upload_ids: channelUploadIds });

export const getReconciliation = (id: string) => api.get(`/reconciliations/${id}`);
export const getMatches = (reconciliationId: string) => api.get(`/reconciliations/${reconciliationId}/matches`);
export const getUnmatchedTransactions = (reconciliationId: string) =>
  api.get(`/reconciliations/${reconciliationId}/unmatched-transactions`);
export const updateMatch = (
  reconciliationId: string,
  matchId: string,
  data: { status: string; reservation_ids?: string[] },
) => api.put(`/reconciliations/${reconciliationId}/matches/${matchId}`, data);
export const confirmAllHigh = (reconciliationId: string) =>
  api.post(`/reconciliations/${reconciliationId}/confirm-all`);

// Invoices
export const generateInvoices = (reconciliationId: string, matchIds?: string[]) =>
  api.post('/invoices/generate/', { reconciliation_id: reconciliationId, match_ids: matchIds });
export const getInvoices = () => api.get('/invoices/');
export const getInvoicePdf = (id: string) => `/api/v1/invoices/${id}/pdf`;

// Labeling (independent ground truth — no system predictions visible)
export const getLabelingDataset = (reconciliationId: string) =>
  api.get(`/labeling/${reconciliationId}/dataset`);
export const getLabels = (reconciliationId: string) =>
  api.get(`/labeling/${reconciliationId}/labels`);
export const saveLabel = (
  reconciliationId: string,
  data: { bank_transaction_id: string; reservation_ids: string[]; label_type: 'match' | 'no_match' },
) => api.post(`/labeling/${reconciliationId}/labels`, data);
export const deleteLabel = (reconciliationId: string, bankTransactionId: string) =>
  api.delete(`/labeling/${reconciliationId}/labels/${bankTransactionId}`);
export const getLabelingProgress = (reconciliationId: string) =>
  api.get(`/labeling/${reconciliationId}/progress`);

export default api;
