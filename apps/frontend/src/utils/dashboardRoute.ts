export type DashboardTab = 'new-study' | 'dashboard' | 'personas' | 'interviews' | 'interview-workspace'
  | 'behavioral-tests' | 'behavioral-test-detail' | 'behavioral-compare' | 'router' | 'study-workflow' | 'evidence' | 'segmentation';

export interface DashboardRoute {
  tab: DashboardTab;
  studyId?: string;
  interviewId?: string;
  testId?: string;
  runId?: string;
  compareRunIds?: string[];
  step?: number;
}

const aliases: Record<string, DashboardTab> = {
  app: 'new-study', 'create-study': 'new-study', 'new-study': 'new-study',
  dashboard: 'dashboard', dataset: 'dashboard', 'data-sources': 'dashboard',
  'persona-library': 'personas', personas: 'personas', router: 'router', provenance: 'router', routes: 'router', models: 'router',
  interviews: 'interviews', 'behavioral-tests': 'behavioral-tests', evidence: 'evidence', segmentation: 'segmentation',
};

export function parseDashboardPath(path: string): DashboardRoute {
  const url = new URL(path, 'https://navigation.invalid');
  const parts = url.pathname.split('/').filter(Boolean);
  const [root, studyId, section, itemId, runSection, runId] = parts;
  if (parts.length === 1 && aliases[root]) return { tab: aliases[root] };
  if (!['research', 'study'].includes(root) || !studyId) return { tab: 'new-study' };
  if (!section) return { tab: 'study-workflow', studyId };
  if (/^step[1-5]$/.test(section) && parts.length === 3) return { tab: 'study-workflow', studyId, step: Number(section.slice(4)) };
  if (section === 'interviews') return itemId
    ? { tab: 'interview-workspace', studyId, interviewId: itemId }
    : { tab: 'interviews', studyId };
  if (section === 'behavioral-tests') {
    if (itemId === 'compare') return { tab: 'behavioral-compare', studyId, compareRunIds: (url.searchParams.get('run_ids') ?? '').split(',').filter(Boolean) };
    return itemId ? { tab: 'behavioral-test-detail', studyId, testId: itemId, runId: runSection === 'runs' ? runId : undefined }
      : { tab: 'behavioral-tests', studyId };
  }
  if (section === 'evidence' || section === 'segmentation') return { tab: section, studyId };
  return { tab: 'new-study' };
}

export function isDashboardPath(path: string): boolean {
  const root = path.split('/').filter(Boolean)[0];
  return root in aliases || root === 'research' || root === 'study';
}

export function isKnownDashboardPath(path: string): boolean {
  const parts = new URL(path, 'https://navigation.invalid').pathname.split('/').filter(Boolean);
  const [root, studyId, section, itemId, runSection, runId] = parts;
  if (parts.length === 1) return root in aliases;
  if (!['research', 'study'].includes(root) || !studyId) return false;
  if (!section) return parts.length === 2;
  if (/^step[1-5]$/.test(section)) return parts.length === 3;
  if (section === 'interviews') return parts.length === 3 || parts.length === 4;
  if (section === 'evidence' || section === 'segmentation') return parts.length === 3;
  if (section !== 'behavioral-tests') return false;
  if (!itemId) return parts.length === 3;
  if (itemId === 'compare') return parts.length === 3;
  if (parts.length === 4) return true;
  return runSection === 'runs' && Boolean(runId) && parts.length === 6;
}

export function safeReturnPath(path: string | null | undefined): string {
  if (!path || !path.startsWith('/') || path.startsWith('//') || /[\\\u0000-\u001f]/.test(path)) return '/app';
  const url = new URL(path, 'https://navigation.invalid');
  if (url.origin !== 'https://navigation.invalid' || !isDashboardPath(url.pathname)) return '/app';
  return `${url.pathname}${url.search}${url.hash}`;
}