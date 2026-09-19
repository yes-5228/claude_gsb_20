import { http } from './client.js';

export const holidayApi = {
  list: (year) => http.get('/holidays', { year }),
  save: (year, entries) => http.put(`/holidays/${year}`, { entries }),
  clear: (year) => http.delete(`/holidays/${year}`),
};
