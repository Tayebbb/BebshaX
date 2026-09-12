import type { DashboardTab } from '../../utils/dashboardRoute';

export const routeModules = {
  'new-study': () => import('./views/NewStudyView').then((module) => ({ default: module.NewStudyView })),
  dashboard: () => import('./views/StudiesDashboardView').then((module) => ({ default: module.StudiesDashboardView })),
  personas: () => import('./views/PersonaLibraryView').then((module) => ({ default: module.PersonaLibraryView })),
  'study-workflow': () => import('./views/StudyWorkflowView').then((module) => ({ default: module.StudyWorkflowView })),
  router: () => import('./views/ModelRouterView').then((module) => ({ default: module.ModelRouterView })),
  evidence: () => import('./views/EvidenceLaboratoryView').then((module) => ({ default: module.EvidenceLaboratoryView })),
  segmentation: () => import('./views/SegmentationView').then((module) => ({ default: module.SegmentationView })),
  interviews: () => import('./views/InterviewsView').then((module) => ({ default: module.InterviewsView })),
  'interview-workspace': () => import('../interview/InterviewWorkspace').then((module) => ({ default: module.InterviewWorkspace })),
  'behavioral-tests': () => import('./views/BehavioralTestingView').then((module) => ({ default: module.BehavioralTestingView })),
  'behavioral-test-detail': () => import('./views/BehavioralTestDetailView').then((module) => ({ default: module.BehavioralTestDetailView })),
  'behavioral-compare': () => import('./views/BehavioralComparisonView').then((module) => ({ default: module.BehavioralComparisonView })),
};

const pending = new Set<DashboardTab>();
const loaded = new Set<DashboardTab>();

export function prefetchDashboardRoute(tab: DashboardTab): void {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (connection?.saveData || connection?.effectiveType === '2g' || pending.size >= 2 || loaded.has(tab) || pending.has(tab)) return;
  pending.add(tab);
  void routeModules[tab]().then(() => { loaded.add(tab); })
    .catch(() => {}).finally(() => { pending.delete(tab); });
}