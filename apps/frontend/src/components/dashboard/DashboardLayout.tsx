import React, { useState, useEffect, useRef } from 'react';
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
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { useTheme } from '../../context/ThemeContext';
import { NewStudyView } from './views/NewStudyView';
import { StudiesDashboardView } from './views/StudiesDashboardView';
import { PersonaLibraryView } from './views/PersonaLibraryView';
import { StudyWorkflowView } from './views/StudyWorkflowView';
import { ModelRouterView } from './views/ModelRouterView';
import { EvidenceLaboratoryView } from './views/EvidenceLaboratoryView';
import { SegmentationView } from './views/SegmentationView';
import { InterviewsView } from './views/InterviewsView';
import { InterviewWorkspace } from '../interview/InterviewWorkspace';
import { BehavioralTestingView } from './views/BehavioralTestingView';
import { BehavioralTestDetailView } from './views/BehavioralTestDetailView';
import { BehavioralComparisonView } from './views/BehavioralComparisonView';
import { StartInterviewModal } from './modals/StartInterviewModal';
import { CreateBehavioralTestModal } from './modals/CreateBehavioralTestModal';
import { StudyType, Study, SyntheticPersona } from '../../types';
import { api } from '../../services/api';
import { BebshaXLogo } from '../common/BebshaXLogo';

export type DashboardTab =
  | 'new-study'
  | 'dashboard'
  | 'personas'
  | 'interviews'
  | 'interview-workspace'
  | 'behavioral-tests'
  | 'behavioral-test-detail'
  | 'behavioral-compare'
  | 'router'
  | 'study-workflow'
  | 'evidence'
  | 'segmentation';

interface DashboardLayoutProps {
  onOpenLandingPage?: () => void;
}

/** Shown wherever a study-scoped view is opened without an active study —
 * a fresh account has none, and inventing an id 404s. */
const NoStudySelected: React.FC<{
  title: string;
  onPickStudy: () => void;
  onCreateStudy: () => void;
}> = ({ title, onPickStudy, onCreateStudy }) => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '12px',
      textAlign: 'center',
      padding: '72px 24px',
      margin: '24px clamp(16px, 4vw, 40px)',
      border: '1px dashed var(--border-subtle)',
      borderRadius: '16px',
      color: 'var(--text-secondary)',
    }}
  >
    <FolderOpen size={28} color="var(--accent-teal)" />
    <div style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)' }}>{title}</div>
    <div style={{ fontSize: '0.88rem', maxWidth: '420px' }}>
      Pick one of your studies to work in, or start a new one.
    </div>
    <div style={{ display: 'flex', gap: '10px', marginTop: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
      <button
        type="button"
        onClick={onPickStudy}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          color: 'var(--text-main)',
          borderRadius: '8px',
          padding: '10px 18px',
          fontSize: '0.85rem',
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        Choose a study
      </button>
      <button
        type="button"
        onClick={onCreateStudy}
        style={{
          background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
          border: 'none',
          color: 'var(--text-on-accent)',
          borderRadius: '8px',
          padding: '10px 18px',
          fontSize: '0.85rem',
          fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        New study
      </button>
    </div>
  </div>
);

const parseDashboardPath = (path: string): {
  tab: DashboardTab;
  studyId?: string;
  interviewId?: string;
  testId?: string;
  runId?: string;
  compareRunIds?: string[];
  step?: number;
} => {
  if (path.includes('/behavioral-tests/compare')) {
    const parts = path.split('?');
    const queryParams = new URLSearchParams(parts[1] || '');
    const runIds = queryParams.get('run_ids')?.split(',').filter(Boolean) || [];
    const pathParts = parts[0].split('/').filter(Boolean);
    const studyId = pathParts[1];
    return { tab: 'behavioral-compare', studyId, compareRunIds: runIds };
  }
  if (path.includes('/behavioral-tests/') && !path.endsWith('/behavioral-tests')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    const testId = parts[3] || parts[2] || '';
    const runId = parts[5] || undefined;
    return { tab: 'behavioral-test-detail', studyId, testId, runId };
  }
  if (path.includes('/behavioral-tests') || path.startsWith('/behavioral-tests')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    return { tab: 'behavioral-tests', studyId };
  }
  if (path.includes('/interviews/') || path.startsWith('/interviews/')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    const interviewId = parts[3] || parts[2] || '';
    return { tab: 'interview-workspace', studyId, interviewId };
  }
  if (path.includes('/interviews') || path.startsWith('/interviews')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    return { tab: 'interviews', studyId };
  }
  if (path.includes('/segmentation') || path.startsWith('/segmentation')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    return { tab: 'segmentation', studyId };
  }
  if (path.includes('/evidence') || path.startsWith('/evidence')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    return { tab: 'evidence', studyId };
  }
  if (path.startsWith('/dataset') || path.startsWith('/data-sources')) {
    return { tab: 'dashboard' };
  }
  if (path.startsWith('/persona-library') || path.startsWith('/personas')) {
    return { tab: 'personas' };
  }
  if (path.startsWith('/router') || path.startsWith('/provenance') || path.startsWith('/routes') || path.startsWith('/models')) {
    return { tab: 'router' };
  }
  if (path.startsWith('/dashboard')) {
    return { tab: 'dashboard' };
  }
  if (path.startsWith('/create-study') || path.startsWith('/new-study') || path === '/app') {
    return { tab: 'new-study' };
  }
  if (path.startsWith('/research') || path.startsWith('/study')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1];
    if (parts[2] === 'behavioral-tests' && parts[3] === 'compare') {
      const queryParams = new URLSearchParams(path.split('?')[1] || '');
      const runIds = queryParams.get('run_ids')?.split(',').filter(Boolean) || [];
      return { tab: 'behavioral-compare', studyId, compareRunIds: runIds };
    }
    if (parts[2] === 'behavioral-tests' && parts[3]) {
      return { tab: 'behavioral-test-detail', studyId, testId: parts[3], runId: parts[5] };
    }
    if (parts[2] === 'behavioral-tests') {
      return { tab: 'behavioral-tests', studyId };
    }
    if (parts[2] === 'interviews' && parts[3]) {
      return { tab: 'interview-workspace', studyId, interviewId: parts[3] };
    }
    if (parts[2] === 'interviews') {
      return { tab: 'interviews', studyId };
    }
    let step = 1;
    if (parts[2] && parts[2].startsWith('step')) {
      const parsed = parseInt(parts[2].replace('step', ''), 10);
      if (!isNaN(parsed) && parsed >= 1 && parsed <= 5) {
        step = parsed;
      }
    }
    return { tab: 'study-workflow', studyId, step };
  }
  return { tab: 'new-study' };
};

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ onOpenLandingPage }) => {
  const { user, logout } = useAuth();
  const { currentPath, navigate } = useNavigation();
  const { theme, toggleTheme } = useTheme();

  const initialParsed = parseDashboardPath(currentPath);
  const [activeTab, setActiveTab] = useState<DashboardTab>(initialParsed.tab);
  const [activeStudyId, setActiveStudyId] = useState<string | undefined>(initialParsed.studyId);
  const [activeInterviewId, setActiveInterviewId] = useState<string | undefined>(initialParsed.interviewId);
  const [activeStep, setActiveStep] = useState<number>(initialParsed.step || 1);

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
  const userMenuAreaRef = useRef<HTMLDivElement | null>(null);
  const userChipRef = useRef<HTMLButtonElement | null>(null);
  const mobileNavTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [showTourHint, setShowTourHint] = useState<boolean>(
    () => localStorage.getItem('bebshax_tour_dismissed') !== '1'
  );

  // Interview & Behavioral Modal State
  const [modalPersona, setModalPersona] = useState<SyntheticPersona | null>(null);
  const [showStartInterviewModal, setShowStartInterviewModal] = useState<boolean>(false);
  const [showCreateBehavioralModal, setShowCreateBehavioralModal] = useState<boolean>(false);
  const [initialBehavioralPersonaId, setInitialBehavioralPersonaId] = useState<string | undefined>(undefined);

  useEffect(() => {
    const parsed = parseDashboardPath(currentPath);
    setActiveTab(parsed.tab);
    if (parsed.studyId) {
      setActiveStudyId(parsed.studyId);
    }
    if (parsed.interviewId) {
      setActiveInterviewId(parsed.interviewId);
    }
    if (parsed.testId) {
      setActiveTestId(parsed.testId);
    }
    if (parsed.runId) {
      setActiveRunId(parsed.runId);
    }
    if (parsed.compareRunIds) {
      setActiveCompareRunIds(parsed.compareRunIds);
    }
    if (parsed.step) {
      setActiveStep(parsed.step);
    }
  }, [currentPath]);

  useEffect(() => {
    const loadRecent = async () => {
      setLoadingRecent(true);
      try {
        const data = await api.getStudies();
        setRecentStudies(data.slice(0, 5));
        setDemoStudy(data.find((s) => s.is_demo) || null);
      } catch {
        // fallback
      } finally {
        setLoadingRecent(false);
        // Mock fixtures must never masquerade as live research data.
        setBackendDown(!api.isMockMode() && !api.isLive());
      }
    };
    loadRecent();
  }, [activeTab]);

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
    if (!showUserMenu) return;
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
  }, [showUserMenu]);

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

  const dismissTourHint = () => {
    localStorage.setItem('bebshax_tour_dismissed', '1');
    setShowTourHint(false);
  };

  /** Study-scoped destinations. Without an active study we stay on the plain
   * tab route, which renders the "pick a study" empty state — inventing a
   * study id here used to 404 every fresh account. */
  const studyScopedPath = (suffix: string): string =>
    activeStudyId ? `/research/${activeStudyId}/${suffix}` : `/${suffix}`;

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
      if (!activeStudyId) {
        navigate('/create-study');
        return;
      }
      navigate(`/research/${activeStudyId}/step1`);
    }
  };

  const handleStartStudy = async (type: StudyType, prompt?: string) => {
    setInitialWorkflowType(type);
    setInitialWorkflowPrompt(prompt);
    setCreateStudyError(null);
    try {
      const created = await api.createStudy({
        type: type,
        prompt: prompt,
        status: 'in_progress',
        step: 1,
      });

      // Optimistically update recent studies list immediately
      setRecentStudies((prev) => [created, ...prev.filter((s) => s.id !== created.id)].slice(0, 5));
      setActiveStudyId(created.id);
      setActiveStep(1);
      navigate(`/research/${created.id}/step1`);
    } catch (err: any) {
      // Never fabricate a study id: the workflow would look fine while every
      // save silently no-ops and the user's work is lost.
      setCreateStudyError(
        err?.message
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

  const navItems = [
    {
      id: 'new-study' as DashboardTab,
      label: 'New Study',
      icon: <PenSquare size={16} />,
    },
    {
      id: 'dashboard' as DashboardTab,
      label: 'Dashboard',
      icon: <LayoutGrid size={16} />,
    },
    {
      id: 'personas' as DashboardTab,
      label: 'Persona Library',
      icon: <Contact2 size={16} />,
    },
    {
      id: 'interviews' as DashboardTab,
      label: 'Interviews',
      icon: <MessageSquare size={16} />,
    },
    {
      id: 'behavioral-tests' as DashboardTab,
      label: 'Behavioral Testing',
      icon: <Sliders size={16} />,
    },
    {
      id: 'evidence' as DashboardTab,
      label: 'Evidence Laboratory',
      icon: <FlaskConical size={16} />,
    },
    {
      id: 'segmentation' as DashboardTab,
      label: 'Audience Segments',
      icon: <PieChart size={16} />,
    },
    {
      id: 'router' as DashboardTab,
      label: 'AI Provider Status',
      icon: <Cpu size={16} />,
    },
  ];

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

      {/* Mobile drawer backdrop */}
      {isMobile && isMobileNavOpen && (
        <div
          onClick={() => setIsMobileNavOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'var(--scrim)', backdropFilter: 'blur(18px) saturate(130%)', WebkitBackdropFilter: 'blur(18px) saturate(130%)', zIndex: 120 }}
        />
      )}

      {/* ============================================================
          LEFT SIDEBAR (Matches Screenshots 1, 2, 3, 4)
         ============================================================ */}
      <aside
        style={{
          width: isSidebarCollapsed ? '72px' : isMobile ? '280px' : '240px',
          background: isMobile ? 'var(--glass-strong)' : 'var(--glass-soft)',
          backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          borderRight: '1px solid var(--fill-soft-2)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: isSidebarCollapsed ? '20px 10px' : '20px 16px',
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
                transition: 'width 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
                zIndex: 40,
              }),
        }}
      >
        {/* Top Brand Header — scrolls internally so the theme toggle and
            user chip below always stay on-screen */}
        <div style={{ minHeight: 0, overflowY: 'auto', overflowX: 'hidden' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              marginBottom: '28px',
              padding: isSidebarCollapsed ? '0' : '0 4px',
            }}
          >
            {!isSidebarCollapsed ? (
              <BebshaXLogo
                size={26}
                textSize="1.15rem"
                onClick={() => navigate('/create-study')}
              />
            ) : (
              <BebshaXLogo
                size={26}
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
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '4px',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <PanelLeft size={16} />
            </button>
          </div>

          {/* Navigation Links */}
          <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '28px' }}>
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleTabClick(item.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    justifyContent: isSidebarCollapsed ? 'center' : 'flex-start',
                    width: '100%',
                    padding: isSidebarCollapsed ? '10px 0' : '10px 12px',
                    borderRadius: '10px',
                    background: isActive ? 'var(--accent-subtle)' : 'transparent',
                    color: isActive ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                    border: isActive ? '1px solid var(--accent-glow)' : '1px solid transparent',
                    fontSize: '0.86rem',
                    fontWeight: isActive ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'all 0.18s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = 'var(--text-main)';
                      e.currentTarget.style.background = 'var(--fill-soft)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = 'var(--text-secondary)';
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span style={{ color: isActive ? 'var(--accent-teal)' : 'var(--text-secondary)' }}>{item.icon}</span>
                  {!isSidebarCollapsed && <span>{item.label}</span>}
                </button>
              );
            })}
          </nav>

          {/* Recent Studies Accordion Section */}
          {!isSidebarCollapsed && (
            <div>
              <button
                type="button"
                onClick={() => setIsRecentStudiesOpen(!isRecentStudiesOpen)}
                aria-expanded={isRecentStudiesOpen}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  background: 'none',
                  border: 'none',
                  fontFamily: 'inherit',
                  textAlign: 'left',
                  padding: '4px 12px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  marginBottom: '6px',
                }}
              >
                <span>Recent Studies</span>
                {isRecentStudiesOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </button>

              {isRecentStudiesOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', paddingLeft: '4px' }}>
                  {loadingRecent ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '6px 8px' }}>
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
                              background: 'transparent',
                              border: 'none',
                              fontFamily: 'inherit',
                              textAlign: 'left',
                              padding: '7px 8px',
                              borderRadius: '8px',
                              fontSize: '0.8rem',
                              color: 'var(--text-secondary)',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              transition: 'color 0.16s ease',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = 'var(--text-main)';
                              e.currentTarget.style.background = 'var(--bg-card)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = 'var(--text-secondary)';
                              e.currentTarget.style.background = 'transparent';
                            }}
                            title={displayTitle}
                          >
                            {isCompleted && (
                              <div
                                style={{
                                  width: '6px',
                                  height: '6px',
                                  borderRadius: '50%',
                                  background: 'var(--accent-emerald)',
                                  flexShrink: 0,
                                }}
                              />
                            )}
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayTitle}</span>
                          </button>
                        );
                      })}

                      <button
                        type="button"
                        onClick={() => handleTabClick('dashboard')}
                        style={{
                          width: '100%',
                          background: 'none',
                          border: 'none',
                          fontFamily: 'inherit',
                          textAlign: 'left',
                          fontSize: '0.78rem',
                          color: 'var(--accent-cyan)',
                          fontWeight: 600,
                          padding: '6px 8px',
                          cursor: 'pointer',
                        }}
                      >
                        See more
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom User Profile Section */}
        <div style={{ position: 'relative' }} ref={userMenuAreaRef}>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: isSidebarCollapsed ? 'center' : 'flex-start',
              gap: '10px',
              width: '100%',
              padding: isSidebarCollapsed ? '8px 0' : '8px 12px',
              marginBottom: '8px',
              borderRadius: '10px',
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'background 0.2s ease, color 0.2s ease',
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
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            {!isSidebarCollapsed && <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>}
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
              gap: '10px',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              width: '100%',
              fontFamily: 'inherit',
              textAlign: 'left',
              padding: isSidebarCollapsed ? '8px 0' : '8px 12px',
              borderRadius: '12px',
              background: showUserMenu ? 'var(--fill-soft-2)' : 'var(--fill-soft)',
              border: 'none',
              outline: 'none',
              cursor: 'pointer',
              transition: 'background 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '9px', minWidth: 0 }}>
              {/* User Avatar (Real Google Avatar or Initial Gradient) */}
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={displayName}
                  referrerPolicy="no-referrer"
                  style={{
                    width: '30px',
                    height: '30px',
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
                    width: '30px',
                    height: '30px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, var(--accent-teal) 0%, var(--accent-cyan) 100%)',
                    color: 'var(--text-on-accent)',
                    fontWeight: 700,
                    fontSize: '0.8rem',
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
                <span
                  style={{
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    color: 'var(--text-main)',
                    letterSpacing: '0.02em',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {displayName}
                </span>
              )}
            </div>

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
                borderRadius: '14px',
                padding: '8px',
                boxShadow: 'inset 0 1px 0 var(--reflect), var(--shadow-lg)',
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
                      background: 'linear-gradient(135deg, var(--accent-teal) 0%, var(--accent-cyan) 100%)',
                      color: 'var(--text-on-accent)',
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
                  color: '#EF4444',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  textAlign: 'left',
                  cursor: 'pointer',
                  borderRadius: '8px',
                  transition: 'background 0.15s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)')}
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
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, position: 'relative', zIndex: 1 }}>
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
              boxSizing: 'border-box',
              padding: '8px 14px',
              background: 'var(--glass-mid)',
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
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                borderRadius: '9px',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <Menu size={18} />
            </button>
            <BebshaXLogo size={22} textSize="1rem" onClick={() => navigate('/create-study')} />
          </div>
        )}

        {/* Top Greeting Header Bar (Screenshot 1) */}
        {activeTab !== 'study-workflow' && (
          <header
            style={{
              padding: '20px clamp(16px, 4vw, 40px) 0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div
              style={{
                fontSize: '0.95rem',
                color: 'var(--text-primary)',
                fontWeight: 500,
                letterSpacing: '-0.01em',
              }}
            >
              {getGreeting()}, {displayName}
            </div>
          </header>
        )}

        {/* First-visit golden-path hint — dismissible, remembered in localStorage */}
        {(activeTab === 'new-study' || activeTab === 'dashboard') && showTourHint && (
          <div
            style={{
              margin: '14px clamp(16px, 4vw, 40px) 0',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: '14px',
              background: 'var(--accent-subtle)',
              border: '1px solid var(--accent-glow)',
              borderRadius: '12px',
              padding: '12px 16px',
            }}
          >
            <div style={{ fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.55 }}>
              <strong style={{ color: 'var(--accent-teal-bright)' }}>New here? The 3-minute tour:</strong>{' '}
              1. Describe your idea → 2. Approve the research goal → 3. Generate personas → 4. Interview one → 5. Generate the report.
            </div>
            <button
              type="button"
              onClick={dismissTourHint}
              aria-label="Dismiss tour hint"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-secondary)',
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
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: '12px',
              padding: '12px 16px',
            }}
          >
            <div style={{ fontSize: '0.85rem', color: 'var(--status-error-text)', lineHeight: 1.55 }}>
              {createStudyError} Nothing was saved — please try again.
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
              background: 'var(--fill-soft)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '12px',
              padding: '12px 16px',
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
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--accent-teal)',
                  color: 'var(--accent-cyan)',
                  borderRadius: '8px',
                  padding: '6px 14px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
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

        {/* Tab View Switcher — keyed so each view replays its entrance */}
        <div
          key={activeTab}
          className="bx-view"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}
        >
        {activeTab === 'new-study' && (
          <NewStudyView
            onStartStudy={handleStartStudy}
            onOpenExampleStudy={
              demoStudy ? () => handleOpenStudy(demoStudy.id, demoStudy.step || 5) : undefined
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
            studyId={activeStudyId}
            onStartInterviewWithPersona={async (pId, fromStudyId) => {
              const sid = fromStudyId || activeStudyId;
              if (!sid) {
                navigate('/dashboard');
                return;
              }
              setActiveStudyId(sid);
              try {
                const p = await api.getStudyPersonaDetail(sid, pId);
                setModalPersona(p);
                setShowStartInterviewModal(true);
              } catch {
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
            onNavigateToEvidence={() => navigate(studyScopedPath('evidence'))}
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
              studyId={activeStudyId}
              interviewId={activeInterviewId}
              onBackToInterviews={() => navigate(`/research/${activeStudyId}/interviews`)}
              onNavigateToPersona={() => navigate('/persona-library')}
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

        {activeTab === 'router' && <ModelRouterView />}

        {activeTab === 'study-workflow' && (
          <StudyWorkflowView
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
                  navigate(`/research/${activeStudyId}/step3`);
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
        </div>
      </main>

      {/* Honest-state banner: fixtures must never pass as live research data */}
      {backendDown && (
        <div
          role="status"
          style={{
            position: 'fixed',
            bottom: '16px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 90,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 16px',
            borderRadius: '999px',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.4)',
            color: '#F59E0B',
            fontSize: '0.78rem',
            fontWeight: 600,
            backdropFilter: 'blur(8px)',
          }}
        >
          {api.isMockMode()
            ? 'Showing sample data — backend unreachable. Data shown here is not live research output.'
            : "Backend unreachable — your studies can't be loaded right now. Nothing shown here is missing data; it simply hasn't loaded."}
        </div>
      )}

      {/* Start Adaptive Interview Modal */}
      {showStartInterviewModal && modalPersona && activeStudyId && (
        <StartInterviewModal
          isOpen={showStartInterviewModal}
          onClose={() => {
            setShowStartInterviewModal(false);
            setModalPersona(null);
          }}
          persona={modalPersona}
          studyId={activeStudyId}
          onInterviewStarted={(newInterviewId) => {
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
            setShowCreateBehavioralModal(false);
            setInitialBehavioralPersonaId(undefined);
          }}
          studyId={activeStudyId}
          initialPersonaId={initialBehavioralPersonaId}
          onTestCreated={(testId, runId) => {
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

    </div>
  );
};
