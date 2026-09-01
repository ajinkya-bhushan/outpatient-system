export const patient = {
  name: 'Marcus Thorne',
  age: '55 yrs',
  sex: 'Male',
  mrn: '88291',
  visit: 'Cardiology Follow-up',
};

export const appointments = [
  {
    time: '08:30 AM',
    name: 'Marcus Thorne',
    meta: '62M',
    reason: 'Cardiology Follow-up',
    icon: 'monitor_heart',
    status: 'Pending Review',
    tone: 'urgent',
  },
  {
    time: '09:15 AM',
    name: 'Sarah Jenkins',
    meta: '45F',
    reason: 'Annual Physical',
    icon: 'stethoscope',
    status: 'Pending Review',
    tone: 'urgent',
  },
  {
    time: '10:00 AM',
    name: 'Robert Chen',
    meta: '58M',
    reason: 'Prescription Renewal',
    icon: 'medication',
    status: 'Not Started',
    tone: 'neutral',
  },
  {
    time: '07:45 AM',
    name: 'Elena Rodriguez',
    meta: '32F',
    reason: 'Lab Results Review',
    icon: 'bloodtype',
    status: 'Synced',
    tone: 'done',
  },
];

export const labs = [
  { name: 'Lipid Panel', detail: 'Cholesterol, Total', value: '185 mg/dL', status: 'Normal', tone: 'normal' },
  { name: 'HbA1c', detail: 'Glycated Hemoglobin', value: '7.2 %', status: 'Abnormal', tone: 'abnormal' },
  { name: 'CBC', detail: 'Hemoglobin', value: '14.5 g/dL', status: 'Normal', tone: 'normal' },
];

export const medications = [
  ['Lisinopril 10mg', '1 tablet PO daily'],
  ['Atorvastatin 20mg', '1 tablet PO at bedtime'],
  ['Metformin 500mg', '1 tablet PO BID with meals'],
];

export const navItems = [
  { key: 'schedule', label: 'Schedule', icon: 'calendar_today' },
  { key: 'schedule', label: 'Queue', icon: 'list_alt', preferredActive: true },
  { key: 'sync', label: 'History', icon: 'history' },
  { key: 'analytics', label: 'Analytics', icon: 'analytics' },
];

export const desktopNavItems = [
  { key: 'schedule', label: 'Patient Dashboard', icon: 'list_alt' },
  { key: 'review', label: 'Clinical History', icon: 'description' },
  { key: 'previsit', label: 'Lab Results', icon: 'science' },
  { key: 'analytics', label: 'Analytics', icon: 'analytics' },
  { key: 'settings', label: 'Settings', icon: 'settings' },
];

export const screens = ['login', 'schedule', 'previsit', 'recording', 'generation', 'review', 'sync', 'analytics'];

export const analyticsKpis = [
  ['timer', 'Time Saved', '4.2', 'mins/encounter', 'vs last week'],
  ['thumb_up', 'Acceptance Rate', '94%', '', 'AI suggestions accepted without edit'],
  ['fact_check', 'Doc Completeness', '98%', '', ''],
  ['code', 'Coding Accuracy', '92%', '', ''],
];
