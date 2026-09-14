import { useDialogA11y } from '../../utils/useDialogA11y';
import React, { Suspense, lazy, useState, useEffect, useLayoutEffect, useRef, useMemo } from 'react';
// Dashboard-only assets: kept out of the landing critical path and loaded
// with this (lazy) chunk. Space Grotesk and Unbounded are used by the
// new-study and interview stylesheets; ui.css by the bx-* component kit.
import '@fontsource/space-grotesk/latin-600.css';
import '@fontsource/space-grotesk/latin-700.css';
import '@fontsource/unbounded/latin-800.css';
import '../ui/ui.css';
import {
  Menu,
  PenSquare,
  LayoutGrid,
  Contact2,
  ChevronDown,
  ChevronRight,
  PanelLeft,
  LogOut,
  Globe,
  Sliders,
  MessageSquare,
  Sun,
  Moon,
  X,
  FlaskConical,
  PieChart,
  Cpu,
  FolderOpen,
  MailWarning,
  Search,
  Command,
  ChevronsUpDown,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { useTheme } from '../../context/ThemeContext';
import { CommandMenu, type CommandItem } from '../ui/CommandMenu';
import { EmptyState } from '../ui/EmptyState';
import { Button } from '../ui/Button';
import { NewStudyView } from './views/NewStudyView';
import { prefetchDashboardRoute, routeModules } from './routeModules';
import { HealthResponse, StudyType, Study, SyntheticPersona } from '../../types';
import { findExampleStudy, EXAMPLE_STUDY_STEP } from '../../utils/exampleStudy';
import { api, STUDIES_CHANGED } from '../../services/api';
import { fromUnknownError } from '../../utils/apiError';
import { BebshaXLogo } from '../common/BebshaXLogo';
import { parseDashboardPath, type DashboardTab } from '../../utils/dashboardRoute';
export { parseDashboardPath, type DashboardTab } from '../../utils/dashboardRoute';

const StudiesDashboardView = lazy(routeModules.dashboard);
const PersonaLibraryView = lazy(routeModules.personas);
const StudyWorkflowView = lazy(routeModules['study-workflow']);
const ModelRouterView = lazy(routeModules.router);
const EvidenceLaboratoryView = lazy(routeModules.evidence);
const SegmentationView = lazy(routeModules.segmentation);
const InterviewsView = lazy(routeModules.interviews);
const InterviewWorkspace = lazy(routeModules['interview-workspace']);
const BehavioralTestingView = lazy(routeModules['behavioral-tests']);
const BehavioralTestDetailView = lazy(routeModules['behavioral-test-detail']);
const BehavioralComparisonView = lazy(routeModules['behavioral-compare']);
const StartInterviewModal = lazy(() => import('./modals/StartInterviewModal').then((module) => ({ default: module.StartInterviewModal })));
const CreateBehavioralTestModal = lazy(() => import('./modals/CreateBehavioralTestModal').then((module) => ({ default: module.CreateBehavioralTestModal })));

const honestPillStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  padding: '8px 12px',
  borderRadius: '6px',
  background: 'var(--status-warn-bg)',
  border: 'none',
  color: 'var(--status-warn-text)',
  fontSize: '0.75rem',
  fontWeight: 500,
  textAlign: 'left',
  maxWidth: '100%',
};

interface DashboardLayoutProps {
  onOpenLandingPage?: () => void;
  /** Backend health (App fetches it once); `demo_mode` drives the cached-results banner. */
  health?: HealthResponse | null;
}

/** Shown wherever a study-scoped view is opened without an active study —
 * a fresh account has none, and inventing an id 404s. */
const NoStudySelected: React.FC<{
  title: string;
  onPickStudy: () => void;
  onCreateStudy: () => void;
}> = ({ title, onPickStudy, onCreateStudy }) => (
  <div style={{ padding: '24px var(--page-x)' }}>
    <EmptyState
      icon={<FolderOpen size={22} />}
      title={title}
      description="Interviews, behavioral tests, evidence and segments all belong to a study. Pick one of your studies to work in, or start a new one."
      actions={
        <>
          <Button variant="secondary" onClick={onPickStudy}>
            Choose a study
          </Button>
          <Button variant="primary" onClick={onCreateStudy}>
            New study
          </Button>
        </>
      }
    />
  </div>
);

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ onOpenLandingPage, health = null }) => {
  const { user, logout } = useAuth();
  const { currentPath, currentSearch, navigate } = useNavigation();
  const currentRoute = `${currentPath}${currentSearch}`;
  const { theme, toggleTheme } = useTheme();
  const routeEpochRef = useRef({ active: false, personaRequest: 0 });

  useLayoutEffect(() => {
    const epoch = { active: true, personaRequest: 0 };
    routeEpochRef.current = epoch;
    return () => { epoch.active = false; };
  }, [currentRoute]);

  const initialParsed = parseDashboardPath(currentRoute);
  const [activeTab, setActiveTab] = useState<DashboardTab>(initialParsed.tab);
  const [activeStudyId, setActiveStudyId] = useState<string | undefined>(initialParsed.studyId);
  // Workspace-level views (Dashboard, Persona Library, Router) carry no study in
  // their route; the last study worked in stays the scope for the Study tabs so
  // a detour through the library never strands the user on "No study selected".
  const studyScopeKey = user?.id ? `bebshax_study_scope_${user.id}` : null;
  const [rememberedStudyId, setRememberedStudyId] = useState<string | undefined>(() => {
    try {
      return (studyScopeKey && sessionStorage.getItem(studyScopeKey)) || undefined;
    } catch {
      return undefined;
    }
  });
  // A study id the server rejected (404/403): typed URLs and deleted studies
  // must not stay the scope of every Study tab (live 2026-09-14: a bogus id in
  // one URL followed the user through Interviews until they picked another study).
  const [invalidStudyId, setInvalidStudyId] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!activeStudyId) return;
    // Cleared here so a study that was rejected earlier can be re-validated if it reappears.
    setInvalidStudyId((current) => (current === activeStudyId ? current : undefined));
    setRememberedStudyId(activeStudyId);
    if (!studyScopeKey) return;
    try {
      sessionStorage.setItem(studyScopeKey, activeStudyId);
    } catch {
      // storage is best-effort
    }
  }, [activeStudyId, studyScopeKey]);
  const forgetRememberedStudy = () => {
    setRememberedStudyId(undefined);
    try {
      if (studyScopeKey) sessionStorage.removeItem(studyScopeKey);
    } catch {
      // ignore
    }
  };
  const candidateStudyId = activeStudyId ?? rememberedStudyId;
  const scopedStudyId = candidateStudyId && candidateStudyId !== invalidStudyId ? candidateStudyId : undefined;
  const [activeInterviewId, setActiveInterviewId] = useState<string | undefined>(initialParsed.interviewId);
  const [activeStep, setActiveStep] = useState<number | undefined>(initialParsed.step);

  const [activeTestId, setActiveTestId] = useState<string | undefined>(initialParsed.testId);
  const [activeRunId, setActiveRunId] = useState<string | undefined>(initialParsed.runId);
  const [activeCompareRunIds, setActiveCompareRunIds] = useState<string[]>(initialParsed.compareRunIds || []);

  const [isSidebarCollapsedState, setIsSidebarCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 900px)').matches,
  );
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  // On mobile the sidebar is a full drawer — never the collapsed rail
  const isSidebarCollapsed = !isMobile && isSidebarCollapsedState;
  const [isRecentStudiesOpen, setIsRecentStudiesOpen] = useState(true);
  const [recentStudies, setRecentStudies] = useState<Study[]>([]);
  const [demoStudy, setDemoStudy] = useState<Study | null>(null);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [backendDown, setBackendDown] = useState(false);
  const [createStudyError, setCreateStudyError] = useState<string | null>(null);
  const [verifyReminderDismissed, setVerifyReminderDismissed] = useState<boolean>(
    () => localStorage.getItem('bebshax_verify_reminder_dismissed') === '1'
  );
  const [initialWorkflowType, setInitialWorkflowType] = useState<StudyType>('interviews');
  const [initialWorkflowPrompt, setInitialWorkflowPrompt] = useState<string | undefined>(undefined);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const userMenuAreaRef = useRef<HTMLDivElement | null>(null);
  const userChipRef = useRef<HTMLButtonElement | null>(null);
  const mobileNavTriggerRef = useRef<HTMLButtonElement | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const mainRef = useRef<HTMLElement | null>(null);
  useDialogA11y(sidebarRef, isMobile && isMobileNavOpen, () => setIsMobileNavOpen(false), {
    suspended: cmdOpen || showUserMenu,
  });
  useLayoutEffect(() => {
    if (sidebarRef.current) sidebarRef.current.inert = isMobile && !isMobileNavOpen;
    if (mainRef.current) mainRef.current.inert = isMobile && isMobileNavOpen;
  }, [isMobile, isMobileNavOpen]);

  // Interview & Behavioral Modal State
  const [modalPersona, setModalPersona] = useState<SyntheticPersona | null>(null);
  /** Control that opened the Start Interview dialog (focus returns there on close). */
  const interviewOpenerRef = useRef<HTMLElement | null>(null);
  const [showStartInterviewModal, setShowStartInterviewModal] = useState<boolean>(false);
  const [showCreateBehavioralModal, setShowCreateBehavioralModal] = useState<boolean>(false);
  const [initialBehavioralPersonaId, setInitialBehavioralPersonaId] = useState<string | undefined>(undefined);
  const renderedRouteEpoch = routeEpochRef.current;

  useLayoutEffect(() => {
    const parsed = parseDashboardPath(currentRoute);
    setShowStartInterviewModal(false);
    setModalPersona(null);
    setShowCreateBehavioralModal(false);
    setInitialBehavioralPersonaId(undefined);
    setActiveTab(parsed.tab);
    setActiveStudyId(parsed.studyId);
    setActiveInterviewId(parsed.interviewId);
    setActiveTestId(parsed.testId);
    setActiveRunId(parsed.runId);
    setActiveCompareRunIds(parsed.compareRunIds ?? []);
    setActiveStep(parsed.step);
  }, [currentRoute]);

  useEffect(() => {
    const epoch = routeEpochRef.current;
    const ownerId = user?.id;
    let cancelled = false;
    const isCurrent = () => !cancelled && epoch.active && api.getStoredUser()?.id === ownerId;
    setRecentStudies((previous) => api.isMockMode()
      ? previous
      : previous.filter((study) => ownerId && study.user_id === ownerId));
    setDemoStudy((previous) => api.isMockMode() || (ownerId && previous?.user_id === ownerId) ? previous : null);
    const loadRecent = async () => {
      try {
        const data = await api.getStudies();
        if (!isCurrent()) return;
        const ownedStudies = api.isMockMode() ? data : data.filter((study) => ownerId && study.user_id === ownerId);
        setRecentStudies(ownedStudies.slice(0, 5));
        setDemoStudy(findExampleStudy(data.filter((study) => study.is_demo === true)));
      } catch {
        if (!isCurrent()) return;
        const cached = api.getStoredUserStudies();
        setRecentStudies(cached.slice(0, 5));
        setDemoStudy(findExampleStudy(cached));
      } finally {
        if (isCurrent()) {
          setLoadingRecent(false);
          // Mock fixtures must never masquerade as live research data.
          setBackendDown(!api.isMockMode() && !api.isLive());
        }
      }
    };
    loadRecent();
    // A study created or deleted from any view must leave the sidebar too; an
    // update only refreshes the rows already shown (no extra round trip).
    const onStudiesChanged = (event: Event) => {
      const changed = (event as CustomEvent<{ studies?: Study[] }>).detail?.studies;
      if (!Array.isArray(changed)) { void loadRecent(); return; }
      const owned = api.isMockMode() ? changed : changed.filter((study) => ownerId && study.user_id === ownerId);
      const known = new Set(owned.map((study) => study.id));
      const newest = owned.reduce<Study | null>((latest, study) => (
        !latest || String(study.created_at) > String(latest.created_at) ? study : latest
      ), null);
      setRecentStudies((previous) => {
        const removed = previous.some((study) => !known.has(study.id));
        const created = newest !== null && !previous.some((study) => study.id === newest.id);
        if (removed || created) { void loadRecent(); return previous; }
        return previous.map((study) => owned.find((candidate) => candidate.id === study.id) ?? study);
      });
    };
    window.addEventListener(STUDIES_CHANGED, onStudiesChanged);
    return () => { cancelled = true; window.removeEventListener(STUDIES_CHANGED, onStudiesChanged); };
  }, [currentPath, user?.id]);

  // Dynamic greeting based on time of day
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const displayName = user?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || 'there';

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(max-width: 900px)');
    const onChange = (e: MediaQueryListEvent) => {
      setIsMobile(e.matches);
      if (!e.matches) setIsMobileNavOpen(false);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  // Escape closes the user popover, clicking anywhere outside it closes it too;
  // focus returns to the chip so keyboard users are not stranded. Capture phase
  // + preventDefault: the popover outranks the drawer (topmost surface wins),
  // and one Escape press never closes more than one surface.
  useEffect(() => {
    if (!showUserMenu || cmdOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowUserMenu(false);
        userChipRef.current?.focus();
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const items = Array.from(
          userMenuAreaRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
        );
        if (items.length === 0) return;
        e.preventDefault();
        const idx = items.indexOf(document.activeElement as HTMLElement);
        const step = e.key === 'ArrowDown' ? 1 : -1;
        items[(idx + step + items.length) % items.length].focus();
      }
    };
    const onPointerDown = (e: MouseEvent) => {
      if (userMenuAreaRef.current && !userMenuAreaRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [showUserMenu, cmdOpen]);

  // Escape closes the mobile nav drawer (backdrop click already does). Bubble
  // phase + defaultPrevented check: the drawer is the lowest-priority surface.
  useEffect(() => {
    if (!isMobileNavOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setIsMobileNavOpen(false);
        mobileNavTriggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [isMobileNavOpen]);

  /** Study-scoped destinations. Without a study in scope we stay on the plain
   * tab route, which renders the "pick a study" empty state — inventing a
   * study id here used to 404 every fresh account. */
  const studyScopedPath = (suffix: string): string =>
    scopedStudyId ? `/research/${scopedStudyId}/${suffix}` : `/${suffix}`;

  const handleTabClick = (tab: DashboardTab) => {
    setIsMobileNavOpen(false);
    if (tab === 'new-study') navigate('/create-study');
    else if (tab === 'dashboard') navigate('/dashboard');
    else if (tab === 'personas') navigate('/persona-library');
    else if (tab === 'interviews') navigate(studyScopedPath('interviews'));
    else if (tab === 'behavioral-tests') navigate(studyScopedPath('behavioral-tests'));
    else if (tab === 'evidence') navigate(studyScopedPath('evidence'));
    else if (tab === 'segmentation') navigate(studyScopedPath('segmentation'));
    else if (tab === 'router') navigate('/router');
    else if (tab === 'study-workflow') {
      setInitialWorkflowPrompt(undefined);
      if (!scopedStudyId) {
        navigate('/create-study');
        return;
      }
      navigate(`/research/${scopedStudyId}/step1`);
    }
  };

  const handleStartStudy = async (type: StudyType, prompt?: string) => {
    const epoch = routeEpochRef.current;
    if (!epoch.active) return;
    setCreateStudyError(null);
    try {
      const created = await api.createStudy({
        type: type,
        prompt: prompt,
        status: 'in_progress',
        step: 1,
      });
      if (!epoch.active) return;

      setInitialWorkflowType(type);
      setInitialWorkflowPrompt(prompt);
      // Optimistically update recent studies list immediately
      setRecentStudies((prev) => [created, ...prev.filter((s) => s.id !== created.id)].slice(0, 5));
      setActiveStudyId(created.id);
      setActiveStep(1);
      navigate(`/research/${created.id}/step1`);
    } catch (err) {
      if (!epoch.active) return;
      // Never fabricate a study id: the workflow would look fine while every
      // save silently no-ops and the user's work is lost.
      setCreateStudyError(
        err instanceof Error && err.message
          ? `We couldn't create your study: ${err.message}`
          : "We couldn't create your study — the server didn't respond. Please try again."
      );
      setInitialWorkflowPrompt(undefined);
    }
  };

  const handleOpenStudy = (studyId: string, step: number = 1) => {
    // Reopening an existing study: never re-seed the copilot chat with the
    // stale creation prompt — saved messages are restored from the study.
    setInitialWorkflowPrompt(undefined);
    setIsMobileNavOpen(false);
    setActiveStudyId(studyId);
    setActiveStep(step);
    navigate(`/research/${studyId}/step${step}`);
  };

  const handleStepChange = (step: number) => {
    setActiveStep(step);
    if (!activeStudyId) {
      navigate('/create-study');
      return;
    }
    navigate(`/research/${activeStudyId}/step${step}`);
  };

  // Routing diagnostics are a developer surface: the endpoints behind it answer
  // 403 to ordinary accounts, so the entry point is hidden rather than broken.
  const isDeveloper = user?.role === 'developer' || user?.role === 'admin';
  const navItems = [
    {
      id: 'new-study' as DashboardTab,
      label: 'New Study',
      icon: <PenSquare size={16} />,
      group: 'workspace' as const,
    },
    {
      id: 'dashboard' as DashboardTab,
      label: 'Dashboard',
      icon: <LayoutGrid size={16} />,
      group: 'workspace' as const,
    },
    {
      id: 'personas' as DashboardTab,
      label: 'Persona Library',
      icon: <Contact2 size={16} />,
      group: 'workspace' as const,
    },
    {
      id: 'interviews' as DashboardTab,
      label: 'Interviews',
      icon: <MessageSquare size={16} />,
      group: 'study' as const,
    },
    {
      id: 'behavioral-tests' as DashboardTab,
      label: 'Behavioral Testing',
      icon: <Sliders size={16} />,
      group: 'study' as const,
    },
    {
      id: 'evidence' as DashboardTab,
      label: 'Evidence Laboratory',
      icon: <FlaskConical size={16} />,
      group: 'study' as const,
    },
    {
      id: 'segmentation' as DashboardTab,
      label: 'Audience Segments',
      icon: <PieChart size={16} />,
      group: 'study' as const,
    },
    {
      id: 'router' as DashboardTab,
      label: 'Routing & Provenance',
      icon: <Cpu size={16} />,
      group: 'system' as const,
    },
  ].filter((item) => item.id !== 'router' || isDeveloper);
  const NAV_GROUPS: { id: 'workspace' | 'study' | 'system'; label: string }[] = [
    { id: 'workspace', label: 'Workspace' },
    { id: 'study', label: 'Study' },
    { id: 'system', label: 'System' },
  ];
  // Tabs that live inside a study map onto the Study group for breadcrumbs.
  const TAB_TO_NAV: Partial<Record<DashboardTab, DashboardTab>> = {
    'interview-workspace': 'interviews',
    'behavioral-test-detail': 'behavioral-tests',
    'behavioral-compare': 'behavioral-tests',
  };
  const activeNavId = TAB_TO_NAV[activeTab] ?? activeTab;
  const activeNav = navItems.find((n) => n.id === activeNavId);
  const activeGroup = NAV_GROUPS.find((g) => g.id === activeNav?.group);

  // Title of the study the Study-group tabs are scoped to. Recent list first;
  // deep links to older studies fetch once.
  const [activeStudyTitle, setActiveStudyTitle] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (!candidateStudyId) {
      setActiveStudyTitle(undefined);
      return;
    }
    const known = recentStudies.find((s) => s.id === candidateStudyId);
    if (known) {
      setActiveStudyTitle(known.title);
      return;
    }
    let cancelled = false;
    const epoch = routeEpochRef.current;
    const remembered = !activeStudyId;
    const rejectScope = () => {
      setInvalidStudyId(candidateStudyId);
      if (remembered) forgetRememberedStudy();
      else if (rememberedStudyId === candidateStudyId) forgetRememberedStudy();
    };
    api
      .getStudyById(candidateStudyId)
      .then((s) => {
        if (cancelled || !epoch.active) return;
        setActiveStudyTitle(s?.title ?? undefined);
        // A study that no longer exists must not keep scoping the tabs.
        if (!s) rejectScope();
      })
      .catch((error: unknown) => {
        if (cancelled || !epoch.active) return;
        setActiveStudyTitle(undefined);
        const status = fromUnknownError(error).status;
        if (status === 404 || status === 403) rejectScope();
      });
    return () => {
      cancelled = true;
    };
  }, [activeStudyId, candidateStudyId, recentStudies, currentPath]);

  // Ctrl/⌘ K jump menu
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);
  const commandItems = useMemo<CommandItem[]>(() => {
    const nav: CommandItem[] = navItems.map((n) => ({
      id: `nav-${n.id}`,
      label: n.label,
      group: n.group === 'study' ? 'Study' : n.group === 'system' ? 'System' : 'Workspace',
      icon: n.icon,
      hint: n.group === 'study' && !scopedStudyId ? 'pick a study' : undefined,
      keywords: n.id === 'router' ? ['ai', 'models', 'provenance', 'routing', 'health'] : undefined,
      onSelect: () => handleTabClick(n.id),
    }));
    const studies: CommandItem[] = recentStudies.map((s) => ({
      id: `study-${s.id}`,
      label: s.title && s.title !== 'Untitled Study' ? s.title : 'Untitled study',
      group: 'Recent studies',
      icon: <FolderOpen size={14} />,
      hint: `Step ${s.step || 1}${s.status === 'completed' ? ' · complete' : ''}`,
      keywords: ['open', 'study', 'research'],
      onSelect: () => handleOpenStudy(s.id, s.step || 1),
    }));
    const actions: CommandItem[] = [
      {
        id: 'act-theme',
        label: theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
        group: 'Actions',
        icon: theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />,
        keywords: ['theme', 'appearance'],
        onSelect: toggleTheme,
      },
      ...(onOpenLandingPage
        ? [
            {
              id: 'act-site',
              label: 'Open marketing site',
              group: 'Actions',
              icon: <Globe size={14} />,
              onSelect: onOpenLandingPage,
            } as CommandItem,
          ]
        : []),
      {
        id: 'act-signout',
        label: 'Sign out',
        group: 'Actions',
        icon: <LogOut size={14} />,
        onSelect: () => {
          logout();
          if (onOpenLandingPage) onOpenLandingPage();
          else navigate('/');
        },
      },
    ];
    return [...nav, ...studies, ...actions];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentStudies, scopedStudyId, theme, onOpenLandingPage]);

  const healthLabel = backendDown
    ? 'Backend unreachable'
    : api.isMockMode()
      ? 'Sample data'
      : health?.demo_mode
        ? 'Demo mode'
        : health
          ? 'Backend connected'
          : 'Connecting…';
  const healthTone = backendDown ? 'error' : api.isMockMode() || health?.demo_mode ? 'warn' : health ? 'success' : undefined;

  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        background: 'var(--bg-pure)',
        color: 'var(--text-main)',
        position: 'relative',
        // 'hidden' would make this a scroll container and break the sidebar's
        // position:sticky; 'clip' clips overflow without doing that.
        overflowX: 'clip',
      }}
    >
      {/* Ambient light field — glass chrome picks up this static glow */}
      <div className="bx-ambient" aria-hidden="true" />

      {/* Keyboard users skip the sidebar entirely */}
      <a href="#bx-main" className="bx-skip-link">
        Skip to main content
      </a>

      <CommandMenu open={cmdOpen} onClose={() => setCmdOpen(false)} items={commandItems} />

      {/* Mobile drawer backdrop */}
      {isMobile && isMobileNavOpen && (
        <div
          onClick={() => setIsMobileNavOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'var(--scrim)', backdropFilter: 'blur(6px) saturate(120%)', WebkitBackdropFilter: 'blur(6px) saturate(120%)', zIndex: 120 }}
        />
      )}

      {/* ============================================================
          LEFT SIDEBAR (Matches Screenshots 1, 2, 3, 4)
         ============================================================ */}
      <aside
        ref={sidebarRef}
        role={isMobile ? 'dialog' : undefined}
        aria-label={isMobile ? 'Workspace navigation' : undefined}
        aria-modal={isMobile && isMobileNavOpen ? true : undefined}
        aria-hidden={isMobile && !isMobileNavOpen ? true : undefined}
        style={{
          width: isSidebarCollapsed ? '72px' : isMobile ? '280px' : '240px',
          background: isMobile ? 'var(--glass-strong)' : 'var(--bg-glass)',
          backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          borderRight: '1px solid var(--border-soft)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: isSidebarCollapsed ? '16px 8px' : '16px 12px',
          flexShrink: 0,
          top: 0,
          height: isMobile ? '100dvh' : '100vh',
          ...(isMobile
            ? {
                position: 'fixed',
                left: 0,
                transform: isMobileNavOpen ? 'translateX(0)' : 'translateX(-105%)',
                transition: 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                boxShadow: isMobileNavOpen ? '0 24px 64px rgba(0, 0, 0, 0.45)' : 'none',
                zIndex: 130,
              }
            : {
                position: 'sticky',
                zIndex: 40,
              }),
        }}
      >
        {/* Top Brand Header — scrolls internally so the theme toggle and
            user chip below always stay on-screen */}
        <div style={{ minHeight: 0, overflowY: 'auto', overflowX: 'hidden', scrollbarWidth: 'none' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              marginBottom: '20px',
              padding: isSidebarCollapsed ? '0' : '2px 4px 0',
            }}
          >
            {!isSidebarCollapsed ? (
              <BebshaXLogo
                size={26}
                showIcon={false}
                onClick={() => navigate('/create-study')}
              />
            ) : (
              <BebshaXLogo
                size={28}
                showText={false}
                onClick={() => navigate('/create-study')}
              />
            )}

            {/* Collapse toggle icon */}
            <button
              type="button"
              aria-label="Toggle sidebar"
              onClick={() => (isMobile ? setIsMobileNavOpen(false) : setIsSidebarCollapsed(!isSidebarCollapsedState))}
              style={{
                width: '28px',
                height: '28px',
                background: 'transparent',
                border: '1px solid transparent',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background-color 0.15s ease, color 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--fill-soft)';
                e.currentTarget.style.color = 'var(--text-main)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = 'var(--text-muted)';
              }}
            >
              <PanelLeft size={15} />
            </button>
          </div>

          {/* Navigation Links — grouped by scope so the console reads as
              Workspace / Study / System instead of a flat list */}
          <nav aria-label="Primary" style={{ marginBottom: '8px' }}>
            {NAV_GROUPS.map((group) => {
              const items = navItems.filter((n) => n.group === group.id);
              const isStudyGroup = group.id === 'study';
              if (items.length === 0 && !isStudyGroup) return null;
              return (
                <div key={group.id} className="bx-nav-group">
                  {!isSidebarCollapsed && (
                    <div className="bx-nav-group__label">
                      <span>{group.label}</span>
                    </div>
                  )}
                  {isStudyGroup && !isSidebarCollapsed && (
                    scopedStudyId ? (
                      <button
                        type="button"
                        className="bx-study-chip"
                        aria-current={activeTab === 'study-workflow' ? 'page' : undefined}
                        onClick={() => handleOpenStudy(scopedStudyId, activeStep || 1)}
                        title={`Open “${activeStudyTitle || 'this study'}” workflow`}
                      >
                        <FolderOpen size={13} color="var(--accent-teal)" aria-hidden="true" />
                        <span className="bx-study-chip__title">{activeStudyTitle || 'Current study'}</span>
                        <span className="bx-study-chip__hint">{activeTab === 'study-workflow' ? `Step ${activeStep || 1}` : 'Open'}</span>
                      </button>
                    ) : (
                      <div className="bx-study-chip bx-study-chip--empty" aria-live="polite">
                        <span className="bx-study-chip__title">No study selected</span>
                      </div>
                    )
                  )}
                  {items.map((item) => {
                    const isActive = activeNavId === item.id;
                    const needsStudy = isStudyGroup && !scopedStudyId;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => handleTabClick(item.id)}
                        onPointerEnter={() => prefetchDashboardRoute(item.id)}
                        onFocus={() => prefetchDashboardRoute(item.id)}
                        aria-current={isActive ? 'page' : undefined}
                        className={`bx-nav-item${isSidebarCollapsed ? ' bx-nav-item--collapsed' : ''}${needsStudy && !isActive ? ' bx-nav-item--muted' : ''}`}
                        title={isSidebarCollapsed ? item.label : needsStudy ? `${item.label} — pick a study first` : undefined}
                      >
                        <span className="bx-nav-item__icon">{item.icon}</span>
                        {!isSidebarCollapsed && <span className="bx-nav-item__label">{item.label}</span>}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </nav>

          {/* Recent Studies Accordion Section */}
          {!isSidebarCollapsed && (
            <div style={{ marginTop: '8px' }}>
              <button
                type="button"
                onClick={() => setIsRecentStudiesOpen(!isRecentStudiesOpen)}
                aria-expanded={isRecentStudiesOpen}
                className="bx-nav-group__label"
                style={{
                  width: '100%',
                  background: 'none',
                  border: 'none',
                  fontFamily: 'inherit',
                  textAlign: 'left',
                  cursor: 'pointer',
                  padding: '5px 10px',
                  borderRadius: '6px',
                  transition: 'background 0.15s ease, color 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--fill-soft)';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--text-muted)';
                }}
              >
                <span>Recent Studies</span>
                {isRecentStudiesOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </button>

              {isRecentStudiesOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', padding: '2px 0 0 2px' }}>
                  {loadingRecent ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '6px 10px' }}>
                      <div style={{ height: '14px', borderRadius: '4px', background: 'var(--fill-soft-2)' }} />
                      <div style={{ height: '14px', width: '75%', borderRadius: '4px', background: 'var(--fill-soft-2)' }} />
                      <div style={{ height: '14px', width: '60%', borderRadius: '4px', background: 'var(--fill-soft-2)' }} />
                    </div>
                  ) : recentStudies.length === 0 ? (
                    <div style={{ padding: '8px 10px', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.45 }}>
                      No studies yet.<br />
                      <button
                        type="button"
                        onClick={() => handleTabClick('new-study')}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          fontFamily: 'inherit',
                          fontSize: 'inherit',
                          color: 'var(--accent-teal)',
                          cursor: 'pointer',
                          fontWeight: 600,
                          textAlign: 'left',
                        }}
                      >
                        Start your first research study
                      </button>
                    </div>
                  ) : (
                    <>
                      {recentStudies.map((st) => {
                        const isCompleted = st.status === 'completed';
                        const displayTitle =
                          st.title && st.title !== 'Untitled Study'
                            ? st.title
                            : st.type === 'interviews'
                            ? 'Customer Discovery Study'
                            : st.type === 'landing_page_test'
                            ? 'Concept & Demand Validation'
                            : st.type === 'ab_test'
                            ? 'Pricing Sensitivity Test'
                            : 'Message Hook Testing';

                        return (
                          <button
                            type="button"
                            key={st.id}
                            onClick={() => handleOpenStudy(st.id, st.step || 1)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              width: '100%',
                              height: '32px',
                              background: 'transparent',
                              border: 'none',
                              fontFamily: 'inherit',
                              textAlign: 'left',
                              padding: '0 10px',
                              borderRadius: '6px',
                              fontSize: '0.8rem',
                              fontWeight: 500,
                              color: 'var(--text-secondary)',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              transition: 'background-color 0.15s ease, color 0.15s ease',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--text-main)';
                              e.currentTarget.style.background = 'var(--fill-soft)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-secondary)';
                              e.currentTarget.style.background = 'transparent';
                            }}
                            title={displayTitle}
                          >
                            {isCompleted ? (
                              <span
                                style={{
                                  width: '6px',
                                  height: '6px',
                                  borderRadius: '50%',
                                  background: 'var(--accent-emerald)',
                                  flexShrink: 0,
                                }}
                              />
                            ) : (
                              <Clock size={12} style={{ flexShrink: 0, opacity: 0.6, color: 'var(--text-muted)' }} />
                            )}
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayTitle}</span>
                          </button>
                        );
                      })}

                      <button
                        type="button"
                        onClick={() => handleTabClick('dashboard')}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '5px',
                          width: '100%',
                          background: 'none',
                          border: 'none',
                          fontFamily: 'inherit',
                          textAlign: 'left',
                          fontSize: '0.76rem',
                          color: 'var(--accent-teal)',
                          fontWeight: 600,
                          padding: '6px 10px',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          transition: 'background-color 0.15s ease, color 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'var(--fill-soft)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'transparent';
                        }}
                      >
                        <span>See more</span>
                        <ArrowRight size={11} />
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom User Profile Section */}
        <div
          style={{
            position: 'relative',
            borderTop: '1px solid var(--border-soft)',
            paddingTop: '10px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
          ref={userMenuAreaRef}
        >
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              gap: '8px',
              width: '100%',
              padding: isSidebarCollapsed ? '8px 0' : '6px 10px',
              borderRadius: '6px',
              background: 'transparent',
              border: '1px solid transparent',
              color: 'var(--text-secondary)',
              fontSize: '0.78rem',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'background-color 0.15s ease, color 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--fill-soft)';
              e.currentTarget.style.color = 'var(--text-main)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {theme === 'dark' ? <Sun size={14} color="var(--text-secondary)" /> : <Moon size={14} color="var(--text-secondary)" />}
              {!isSidebarCollapsed && <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>}
            </div>
            {!isSidebarCollapsed && (
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  letterSpacing: '0',
                  padding: '2px 7px',
                  borderRadius: '4px',
                  background: 'var(--fill-soft-2)',
                  color: 'var(--text-secondary)',
                }}
              >
                {theme === 'dark' ? 'Dark' : 'Light'}
              </span>
            )}
          </button>
          <button
            type="button"
            ref={userChipRef}
            onClick={() => setShowUserMenu(!showUserMenu)}
            aria-haspopup="menu"
            aria-expanded={showUserMenu}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '9px',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              width: '100%',
              fontFamily: 'inherit',
              textAlign: 'left',
              padding: isSidebarCollapsed ? '6px 0' : '6px 8px',
              borderRadius: '6px',
              background: showUserMenu ? 'var(--fill-soft-2)' : 'transparent',
              border: 'none',
              outline: 'none',
              cursor: 'pointer',
              transition: 'background-color 0.15s ease, color 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--fill-soft-2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = showUserMenu ? 'var(--fill-soft-2)' : 'transparent';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '9px', minWidth: 0 }}>
              {/* User Avatar */}
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={displayName}
                  referrerPolicy="no-referrer"
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    objectFit: 'cover',
                    border: 'none',
                    outline: 'none',
                    flexShrink: 0,
                  }}
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    background: 'var(--fill-soft-2)',
                    color: 'var(--text-main)',
                    fontWeight: 600,
                    fontSize: '0.78rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  {displayName.charAt(0).toUpperCase()}
                </div>
              )}

              {!isSidebarCollapsed && (
                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
                  <span
                    style={{
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      color: 'var(--text-main)',
                      letterSpacing: '0',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      lineHeight: 1.25,
                    }}
                  >
                    {displayName}
                  </span>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      color: 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      lineHeight: 1.2,
                    }}
                  >
                    {user?.email || 'BebshaX Workspace'}
                  </span>
                </div>
              )}
            </div>

            {!isSidebarCollapsed && (
              <ChevronsUpDown size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
            )}
          </button>

          {/* User Popover Menu */}
          {showUserMenu && (
            <div
              role="menu"
              aria-label="User menu"
              style={{
                position: 'absolute',
                bottom: '100%',
                left: 0,
                marginBottom: '8px',
                width: isSidebarCollapsed ? '220px' : '100%',
                background: 'var(--glass-strong)',
                backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
                WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
                border: '1px solid var(--border-soft)',
                outline: 'none',
                borderRadius: '8px',
                padding: '8px',
                boxShadow: 'var(--shadow-lg)',
                zIndex: 50,
              }}
            >
              {/* User Info Header */}
              <div
                style={{
                  padding: '6px 8px 10px 8px',
                  borderBottom: '1px solid var(--fill-soft-2)',
                  marginBottom: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '9px',
                }}
              >
                {user?.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={displayName}
                    referrerPolicy="no-referrer"
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      objectFit: 'cover',
                      border: 'none',
                      outline: 'none',
                      flexShrink: 0,
                    }}
                    onError={(e) => {
                      (e.currentTarget as HTMLImageElement).style.display = 'none';
                    }}
                  />
                ) : (
                  <div
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      background: 'var(--fill-soft-2)',
                      color: 'var(--text-main)',
                      fontWeight: 700,
                      fontSize: '0.82rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {displayName.charAt(0)}
                  </div>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: '0.84rem',
                      fontWeight: 600,
                      color: 'var(--text-main)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {user?.full_name || displayName}
                  </span>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      color: 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {user?.email || 'Logged in'}
                  </span>
                </div>
              </div>

              {onOpenLandingPage && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setShowUserMenu(false);
                    onOpenLandingPage();
                  }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 10px',
                    background: 'transparent',
                    border: 'none',
                    outline: 'none',
                    color: 'var(--text-main)',
                    fontSize: '0.82rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    borderRadius: '8px',
                    transition: 'background 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--fill-soft)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <Globe size={14} /> Marketing Site
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setShowUserMenu(false);
                  logout();
                  if (onOpenLandingPage) {
                    onOpenLandingPage();
                  } else {
                    navigate('/');
                  }
                }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 10px',
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--status-error-text)',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  textAlign: 'left',
                  cursor: 'pointer',
                  borderRadius: '8px',
                  transition: 'background 0.15s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--status-error-bg)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <LogOut size={14} /> Sign Out
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* ============================================================
          MAIN VIEW AREA
         ============================================================ */}
      <main ref={mainRef} id="bx-main" tabIndex={-1} style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, position: 'relative', zIndex: 1, outline: 'none' }}>
        {/* Mobile top bar — opens the nav drawer */}
        {isMobile && (
          <div
            style={{
              position: 'sticky',
              top: 0,
              zIndex: 95,
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              minHeight: '52px',
              height: '52px',
              boxSizing: 'border-box',
              padding: '0px 14px',
              background: 'var(--bg-primary)',
              backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
              WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
              borderBottom: '1px solid var(--border-soft)',
            }}
          >
            <button
              type="button"
              ref={mobileNavTriggerRef}
              aria-label="Open navigation"
              onClick={() => setIsMobileNavOpen(true)}
              style={{
                background: 'var(--fill-soft)',
                border: 'none',
                color: 'var(--text-primary)',
                borderRadius: '6px',
                width: '44px',
                height: '44px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <Menu size={18} />
            </button>
            <BebshaXLogo size={26} showIcon={false} onClick={() => navigate('/create-study')} />
          </div>
        )}

        {/* Top bar — where am I, jump anywhere, is the backend alive */}
        {activeTab !== 'study-workflow' && (
          <header className="bx-topbar">
            <nav className="bx-topbar__crumbs" aria-label="Breadcrumb">
              <ol>
                {activeGroup && <li>{activeGroup.label}</li>}
                {activeGroup && activeNav && (
                  <li aria-hidden="true" className="bx-topbar__crumb-sep">
                    <ChevronRight size={13} />
                  </li>
                )}
                {activeNav && <li aria-current="page">{activeNav.label}</li>}
                {activeNav?.group === 'study' && activeStudyTitle && (
                  <>
                    <li aria-hidden="true" className="bx-topbar__crumb-sep">
                      <ChevronRight size={13} />
                    </li>
                    <li style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>{activeStudyTitle}</li>
                  </>
                )}
              </ol>
            </nav>
            <div className="bx-topbar__right">
              <span className="bx-topbar__greeting">
                {getGreeting()}, {displayName}
              </span>
              <button
                type="button"
                className="bx-cmdk-trigger"
                onClick={() => setCmdOpen(true)}
                aria-label="Open command menu"
                aria-keyshortcuts={isMac ? 'Meta+K' : 'Control+K'}
              >
                <Search size={14} aria-hidden="true" />
                <span className="bx-cmdk-trigger__label">Search or jump to…</span>
                <span className="bx-cmdk-trigger__keys" aria-hidden="true">
                  <span className="bx-kbd">{isMac ? <Command size={9} /> : 'Ctrl'}</span>
                  <span className="bx-kbd">K</span>
                </span>
              </button>
              <span className="bx-health" role="status" title={healthLabel}>
                <span className={`bx-dot${healthTone ? ` bx-dot--${healthTone}` : ''}${healthTone === 'success' ? ' bx-dot--live' : ''}`} aria-hidden="true" />
                <span className="bx-health__label">{healthLabel}</span>
              </span>
            </div>
          </header>
        )}

        {/* Study creation failed — say so and stay put; no fabricated study id. */}
        {createStudyError && (
          <div
            role="alert"
            style={{
              margin: '14px clamp(16px, 4vw, 40px) 0',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: '14px',
              background: 'var(--status-error-bg)',
              border: 'none',
              borderRadius: '14px',
              padding: '12px 16px',
            }}
          >
            <div style={{ fontSize: '0.85rem', color: 'var(--status-error-text)', lineHeight: 1.55 }}>
              {createStudyError} Check Dashboard before retrying to avoid creating a duplicate.
            </div>
            <button
              type="button"
              onClick={() => setCreateStudyError(null)}
              aria-label="Dismiss study creation error"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--status-error-text)',
                cursor: 'pointer',
                padding: '2px',
                flexShrink: 0,
                display: 'flex',
              }}
            >
              <X size={15} />
            </button>
          </div>
        )}

        {/* Dismissible reminder — the backend already authenticated this user,
            so verification is a nudge, never a wall. */}
        {user && user.is_verified === false && !verifyReminderDismissed && (
          <div
            role="status"
            style={{
              margin: '14px clamp(16px, 4vw, 40px) 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '14px',
              flexWrap: 'wrap',
              background: 'var(--bg-card)',
              border: 'none',
              borderRadius: '14px',
              padding: '12px 16px',
              boxShadow: 'inset 0 1px 0 var(--reflect)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.84rem', color: 'var(--text-primary)' }}>
              <MailWarning size={16} color="var(--status-warn-text)" />
              Your email isn&apos;t verified yet. You can keep working — verify when convenient.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                onClick={() => navigate('/auth/verify')}
                className="bx-btn bx-btn--tinted bx-btn--sm"
              >
                Verify email
              </button>
              <button
                type="button"
                onClick={() => {
                  localStorage.setItem('bebshax_verify_reminder_dismissed', '1');
                  setVerifyReminderDismissed(true);
                }}
                aria-label="Dismiss email verification reminder"
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  padding: '2px',
                  display: 'flex',
                }}
              >
                <X size={15} />
              </button>
            </div>
          </div>
        )}

        {(backendDown || api.isMockMode() || health?.demo_mode) && (
          <div
            style={{
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'stretch',
              gap: '8px',
              padding: '12px var(--page-x)',
              flexShrink: 0,
            }}
          >
            {backendDown && (
              <div role="status" style={honestPillStyle}>
                Backend unreachable — your studies can&apos;t be loaded right now. Nothing shown here is missing data; it simply hasn&apos;t loaded.
              </div>
            )}
            {api.isMockMode() && (
              <div role="status" data-testid="mock-mode-banner" style={honestPillStyle}>
                Showing sample data (mock mode) — nothing here is live research output.
              </div>
            )}
            {health?.demo_mode && (
              <div role="status" data-testid="demo-mode-banner" style={{ ...honestPillStyle, color: 'var(--accent-primary)', background: 'var(--status-info-bg)' }}>
                Demo mode — cached results are labeled CACHED wherever they appear.
              </div>
            )}
          </div>
        )}

        {/* Tab View Switcher — keyed so each view replays its entrance */}
        <div
          key={activeTab}
          className="bx-view"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}
        >
        <Suspense fallback={<div role="status" className="bx-loading" style={{ padding: 24 }}>Loading view...</div>}>
        {activeTab === 'new-study' && (
          <NewStudyView
            onStartStudy={handleStartStudy}
            onOpenExampleStudy={
              demoStudy ? () => handleOpenStudy(demoStudy.id, EXAMPLE_STUDY_STEP) : undefined
            }
          />
        )}

        {activeTab === 'dashboard' && (
          <StudiesDashboardView
            onCreateStudy={() => navigate('/create-study')}
            onOpenStudy={handleOpenStudy}
          />
        )}

        {activeTab === 'personas' && (
          <PersonaLibraryView
            studyId={scopedStudyId}
            initialPersonaId={new URLSearchParams(currentSearch).get('persona') ?? undefined}
            onStudyChange={(sid) => { if (sid) setActiveStudyId(sid); }}
            onStartInterviewWithPersona={async (pId, fromStudyId) => {
              const epoch = routeEpochRef.current;
              if (!epoch.active) return;
              const requestId = ++epoch.personaRequest;
              // Remember the opener now: the persona load below re-renders the library.
              interviewOpenerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
              const sid = fromStudyId || activeStudyId;
              if (!sid) {
                navigate('/dashboard');
                return;
              }
              setActiveStudyId(sid);
              try {
                const p = await api.getStudyPersonaDetail(sid, pId);
                if (!epoch.active || epoch.personaRequest !== requestId) return;
                setModalPersona(p);
                setShowStartInterviewModal(true);
              } catch {
                if (!epoch.active || epoch.personaRequest !== requestId) return;
                navigate(`/research/${sid}/interviews`);
              }
            }}
            onTestBehaviorWithPersona={(pId, fromStudyId) => {
              const sid = fromStudyId || activeStudyId;
              if (!sid) {
                navigate('/dashboard');
                return;
              }
              setActiveStudyId(sid);
              setInitialBehavioralPersonaId(pId);
              setShowCreateBehavioralModal(true);
            }}
            onNavigateToEvidence={(fromStudyId) => navigate(`/research/${fromStudyId}/evidence`)}
            onNavigateToSegmentation={() => navigate(studyScopedPath('segmentation'))}
          />
        )}

        {activeTab === 'interviews' &&
          (activeStudyId ? (
            <InterviewsView
              studyId={activeStudyId}
              onOpenInterview={(intId) => {
                setActiveInterviewId(intId);
                navigate(`/research/${activeStudyId}/interviews/${intId}`);
              }}
              onNavigateToPersonas={() => navigate('/persona-library')}
            />
          ) : (
            <NoStudySelected
              title="No study selected for interviews"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}

        {activeTab === 'interview-workspace' &&
          activeInterviewId &&
          (activeStudyId ? (
            <InterviewWorkspace
              key={`${activeStudyId}:${activeInterviewId}`}
              studyId={activeStudyId}
              interviewId={activeInterviewId}
              onBackToInterviews={() => navigate(`/research/${activeStudyId}/interviews`)}
              onNavigateToPersona={(personaId) => navigate(personaId ? `/persona-library?persona=${encodeURIComponent(personaId)}` : '/persona-library')}
            />
          ) : (
            <NoStudySelected
              title="No study selected for this interview"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}

        {activeTab === 'behavioral-tests' &&
          (activeStudyId ? (
            <BehavioralTestingView
              studyId={activeStudyId}
              onOpenTest={(testId, runId) => {
                setActiveTestId(testId);
                setActiveRunId(runId);
                navigate(
                  runId
                    ? `/research/${activeStudyId}/behavioral-tests/${testId}/runs/${runId}`
                    : `/research/${activeStudyId}/behavioral-tests/${testId}`
                );
              }}
              onCompareRuns={(runIds) => {
                setActiveCompareRunIds(runIds);
                navigate(`/research/${activeStudyId}/behavioral-tests/compare?run_ids=${runIds.join(',')}`);
              }}
              onNavigateToPersonas={() => navigate('/persona-library')}
            />
          ) : (
            <NoStudySelected
              title="No study selected for behavioral testing"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}

        {activeTab === 'behavioral-test-detail' && activeTestId && activeStudyId && (
          <BehavioralTestDetailView
            studyId={activeStudyId}
            testId={activeTestId}
            initialRunId={activeRunId}
            onBack={() => navigate(`/research/${activeStudyId}/behavioral-tests`)}
            onCompareRuns={(runIds) => {
              setActiveCompareRunIds(runIds);
              navigate(`/research/${activeStudyId}/behavioral-tests/compare?run_ids=${runIds.join(',')}`);
            }}
            onNavigateToPersona={() => navigate('/persona-library')}
          />
        )}

        {activeTab === 'behavioral-compare' &&
          (activeStudyId ? (
            <BehavioralComparisonView
              studyId={activeStudyId}
              runIds={activeCompareRunIds}
              onBack={() => navigate(`/research/${activeStudyId}/behavioral-tests`)}
            />
          ) : (
            <NoStudySelected
              title="No study selected for this comparison"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}

        {activeTab === 'router' && (isDeveloper ? <ModelRouterView /> : (
          <div style={{ padding: '32px var(--page-x)' }}>
            <EmptyState
              icon={<Cpu size={22} aria-hidden="true" />}
              title="Developer access required"
              description="Routing diagnostics are available to developer and admin accounts. Your research workspace is still available."
              actions={<Button variant="secondary" onClick={() => navigate('/dashboard')}>Back to studies</Button>}
            />
          </div>
        ))}

        {activeTab === 'study-workflow' && (
          <StudyWorkflowView
            key={activeStudyId}
            studyId={activeStudyId}
            initialStep={activeStep}
            initialType={initialWorkflowType}
            initialPrompt={initialWorkflowPrompt}
            onStepChange={handleStepChange}
            onExit={() => navigate('/dashboard')}
          />
        )}

        {activeTab === 'evidence' &&
          (activeStudyId ? (
            <EvidenceLaboratoryView studyId={activeStudyId} onBack={() => navigate('/dashboard')} />
          ) : (
            <NoStudySelected
              title="No study selected for the evidence laboratory"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}

        {activeTab === 'segmentation' &&
          (activeStudyId ? (
            <div style={{ padding: '24px clamp(16px, 4vw, 40px)' }}>
              <SegmentationView
                studyId={activeStudyId}
                onNavigateToEvidence={() => navigate(`/research/${activeStudyId}/evidence`)}
                onProceedToPersonas={() => {
                  navigate(`/research/${activeStudyId}/step2`);
                }}
              />
            </div>
          ) : (
            <NoStudySelected
              title="No study selected for audience segments"
              onPickStudy={() => navigate('/dashboard')}
              onCreateStudy={() => navigate('/create-study')}
            />
          ))}
        </Suspense>
        </div>
      </main>

      {/* Start Adaptive Interview Modal */}
      <Suspense fallback={<div role="status">Loading dialog...</div>}>
      {showStartInterviewModal && modalPersona && activeStudyId && (
        <StartInterviewModal
          isOpen={showStartInterviewModal}
          onClose={() => {
            if (!renderedRouteEpoch.active) return;
            renderedRouteEpoch.personaRequest += 1;
            setShowStartInterviewModal(false);
            setModalPersona(null);
          }}
          persona={modalPersona}
          studyId={activeStudyId}
          returnFocusTo={interviewOpenerRef}
          onInterviewStarted={(newInterviewId) => {
            if (!renderedRouteEpoch.active) return;
            setActiveInterviewId(newInterviewId);
            navigate(`/research/${activeStudyId}/interviews/${newInterviewId}`);
          }}
        />
      )}

      {/* Create Behavioral Simulation Modal */}
      {showCreateBehavioralModal && activeStudyId && (
        <CreateBehavioralTestModal
          isOpen={showCreateBehavioralModal}
          onClose={() => {
            if (!renderedRouteEpoch.active) return;
            setShowCreateBehavioralModal(false);
            setInitialBehavioralPersonaId(undefined);
          }}
          studyId={activeStudyId}
          initialPersonaId={initialBehavioralPersonaId}
          onTestCreated={(testId, runId) => {
            if (!renderedRouteEpoch.active) return;
            setActiveTestId(testId);
            setActiveRunId(runId);
            navigate(
              runId
                ? `/research/${activeStudyId}/behavioral-tests/${testId}/runs/${runId}`
                : `/research/${activeStudyId}/behavioral-tests/${testId}`
            );
          }}
        />
      )}
      </Suspense>

    </div>
  );
};
