import { http } from './client.js';

export const deadlineApi = {
  rules: () => http.get('/deadline/rules'),
  saveRules: (rules) => http.put('/deadline/rules', { rules }),
  preview: (category, severity, reportTime) =>
    http.get('/deadline/preview', {
      category,
      severity,
      report_time: reportTime || undefined,
    }),
  holidays: (year) => http.get('/calendar/holidays', { year }),
  saveHolidays: (year, holidays) => http.put('/calendar/holidays', { year, holidays }),
};
