import React, { useState, useEffect } from 'react';
import {
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
    const studyId = pathParts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    return { tab: 'behavioral-compare', studyId, compareRunIds: runIds };
  }
  if (path.includes('/behavioral-tests/') && !path.endsWith('/behavioral-tests')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    const testId = parts[3] || parts[2] || '';
    const runId = parts[5] || undefined;
    return { tab: 'behavioral-test-detail', studyId, testId, runId };
  }
  if (path.includes('/behavioral-tests') || path.startsWith('/behavioral-tests')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    return { tab: 'behavioral-tests', studyId };
  }
  if (path.includes('/interviews/') || path.startsWith('/interviews/')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    const interviewId = parts[3] || parts[2] || '';
    return { tab: 'interview-workspace', studyId, interviewId };
  }
  if (path.includes('/interviews') || path.startsWith('/interviews')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    return { tab: 'interviews', studyId };
  }
  if (path.includes('/segmentation') || path.startsWith('/segmentation')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
    return { tab: 'segmentation', studyId };
  }
  if (path.includes('/evidence') || path.startsWith('/evidence')) {
    const parts = path.split('/').filter(Boolean);
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
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
    const studyId = parts[1] || 'tj6FY3cXDO8oxpuxeAMb';
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

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isRecentStudiesOpen, setIsRecentStudiesOpen] = useState(true);
  const [recentStudies, setRecentStudies] = useState<Study[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [initialWorkflowType, setInitialWorkflowType] = useState<StudyType>('interviews');
  const [initialWorkflowPrompt, setInitialWorkflowPrompt] = useState<string | undefined>(undefined);
  const [showUserMenu, setShowUserMenu] = useState(false);

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
      } catch {
        // fallback
      } finally {
        setLoadingRecent(false);
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

  const handleTabClick = (tab: DashboardTab) => {
    if (tab === 'new-study') navigate('/create-study');
    else if (tab === 'dashboard') navigate('/dashboard');
    else if (tab === 'personas') navigate('/persona-library');
    else if (tab === 'interviews') navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/interviews`);
    else if (tab === 'behavioral-tests') navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests`);
    else if (tab === 'router') navigate('/router');
    else if (tab === 'study-workflow') {
      setInitialWorkflowPrompt(undefined);
      navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/step1`);
    }
  };

  const handleStartStudy = async (type: StudyType, prompt?: string) => {
    setInitialWorkflowType(type);
    setInitialWorkflowPrompt(prompt);
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
    } catch {
      const fallbackId = `study_${Date.now()}`;
      setActiveStudyId(fallbackId);
      setActiveStep(1);
      navigate(`/research/${fallbackId}/step1`);
    }
  };

  const handleOpenStudy = (studyId: string, step: number = 1) => {
    // Reopening an existing study: never re-seed the copilot chat with the
    // stale creation prompt — saved messages are restored from the study.
    setInitialWorkflowPrompt(undefined);
    setActiveStudyId(studyId);
    setActiveStep(step);
    navigate(`/research/${studyId}/step${step}`);
  };

  const handleStepChange = (step: number) => {
    setActiveStep(step);
    navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/step${step}`);
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
      {/* ============================================================
          LEFT SIDEBAR (Matches Screenshots 1, 2, 3, 4)
         ============================================================ */}
      <aside
        style={{
          width: isSidebarCollapsed ? '72px' : '240px',
          background: 'var(--bg-pure)',
          borderRight: '1px solid var(--fill-soft-2)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: isSidebarCollapsed ? '20px 10px' : '20px 16px',
          transition: 'width 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
          flexShrink: 0,
          position: 'sticky',
          top: 0,
          height: '100vh',
          zIndex: 40,
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
              onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
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
                  <span style={{ color: isActive ? '#14B8A6' : 'var(--text-secondary)' }}>{item.icon}</span>
                  {!isSidebarCollapsed && <span>{item.label}</span>}
                </button>
              );
            })}
          </nav>

          {/* Recent Studies Accordion Section */}
          {!isSidebarCollapsed && (
            <div>
              <div
                onClick={() => setIsRecentStudiesOpen(!isRecentStudiesOpen)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
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
              </div>

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
                      <span
                        onClick={() => handleTabClick('new-study')}
                        style={{ color: '#14B8A6', cursor: 'pointer', fontWeight: 600 }}
                      >
                        Start your first research study
                      </span>
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
                          <div
                            key={st.id}
                            onClick={() => handleOpenStudy(st.id)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
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
                          </div>
                        );
                      })}

                      <div
                        onClick={() => handleTabClick('dashboard')}
                        style={{
                          fontSize: '0.78rem',
                          color: 'var(--accent-cyan)',
                          fontWeight: 600,
                          padding: '6px 8px',
                          cursor: 'pointer',
                        }}
                      >
                        See more
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom User Profile Section */}
        <div style={{ position: 'relative' }}>
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
          <div
            onClick={() => setShowUserMenu(!showUserMenu)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
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
                    background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
                    color: 'var(--text-main)',
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

            {!isSidebarCollapsed && (
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  color: 'var(--status-warn-text)',
                  background: 'rgba(246, 200, 120, 0.12)',
                  border: 'none',
                  outline: 'none',
                  padding: '2px 7px',
                  borderRadius: '6px',
                }}
              >
                1 left
              </span>
            )}
          </div>

          {/* User Popover Menu */}
          {showUserMenu && (
            <div
              style={{
                position: 'absolute',
                bottom: '100%',
                left: 0,
                marginBottom: '8px',
                width: isSidebarCollapsed ? '220px' : '100%',
                background: '#141619',
                border: 'none',
                outline: 'none',
                borderRadius: '14px',
                padding: '8px',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.85)',
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
                      background: 'linear-gradient(135deg, var(--status-warn-text) 0%, #D4AF37 100%)',
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
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Top Greeting Header Bar (Screenshot 1) */}
        {activeTab !== 'study-workflow' && (
          <header
            style={{
              padding: '24px 40px 0 40px',
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

        {/* Tab View Switcher — keyed so each view replays its entrance */}
        <div
          key={activeTab}
          className="bx-view"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}
        >
        {activeTab === 'new-study' && (
          <NewStudyView onStartStudy={handleStartStudy} />
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
            onStartInterviewWithPersona={async (pId) => {
              try {
                const p = await api.getStudyPersonaDetail(activeStudyId || 'tj6FY3cXDO8oxpuxeAMb', pId);
                setModalPersona(p);
                setShowStartInterviewModal(true);
              } catch {
                navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/interviews`);
              }
            }}
            onTestBehaviorWithPersona={(pId) => {
              setInitialBehavioralPersonaId(pId);
              setShowCreateBehavioralModal(true);
            }}
            onNavigateToEvidence={() => navigate(`/research/${activeStudyId || 'study_default'}/evidence`)}
            onNavigateToSegmentation={() => navigate(`/research/${activeStudyId || 'study_default'}/segmentation`)}
          />
        )}

        {activeTab === 'interviews' && (
          <InterviewsView
            studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
            onOpenInterview={(intId) => {
              setActiveInterviewId(intId);
              navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/interviews/${intId}`);
            }}
            onNavigateToPersonas={() => navigate('/persona-library')}
          />
        )}

        {activeTab === 'interview-workspace' && activeInterviewId && (
          <InterviewWorkspace
            studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
            interviewId={activeInterviewId}
            onBackToInterviews={() => navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/interviews`)}
            onNavigateToPersona={() => navigate('/persona-library')}
          />
        )}

        {activeTab === 'behavioral-tests' && (
          <BehavioralTestingView
            studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
            onOpenTest={(testId, runId) => {
              setActiveTestId(testId);
              setActiveRunId(runId);
              navigate(
                runId
                  ? `/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/${testId}/runs/${runId}`
                  : `/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/${testId}`
              );
            }}
            onCompareRuns={(runIds) => {
              setActiveCompareRunIds(runIds);
              navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/compare?run_ids=${runIds.join(',')}`);
            }}
            onNavigateToPersonas={() => navigate('/persona-library')}
          />
        )}

        {activeTab === 'behavioral-test-detail' && activeTestId && (
          <BehavioralTestDetailView
            studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
            testId={activeTestId}
            initialRunId={activeRunId}
            onBack={() => navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests`)}
            onCompareRuns={(runIds) => {
              setActiveCompareRunIds(runIds);
              navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/compare?run_ids=${runIds.join(',')}`);
            }}
            onNavigateToPersona={() => navigate('/persona-library')}
          />
        )}

        {activeTab === 'behavioral-compare' && (
          <BehavioralComparisonView
            studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
            runIds={activeCompareRunIds}
            onBack={() => navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests`)}
          />
        )}

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

        {activeTab === 'evidence' && (
          <EvidenceLaboratoryView
            studyId={activeStudyId || 'study_default'}
            onBack={() => navigate('/dashboard')}
          />
        )}

        {activeTab === 'segmentation' && (
          <div style={{ padding: '24px 40px' }}>
            <SegmentationView
              studyId={activeStudyId || 'study_default'}
              onNavigateToEvidence={() => navigate(`/research/${activeStudyId || 'study_default'}/evidence`)}
              onProceedToPersonas={() => {
                navigate(`/research/${activeStudyId || 'study_default'}/step3`);
              }}
            />
          </div>
        )}
        </div>
      </main>

      {/* Start Adaptive Interview Modal */}
      {showStartInterviewModal && modalPersona && (
        <StartInterviewModal
          isOpen={showStartInterviewModal}
          onClose={() => {
            setShowStartInterviewModal(false);
            setModalPersona(null);
          }}
          persona={modalPersona}
          studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
          onInterviewStarted={(newInterviewId) => {
            setActiveInterviewId(newInterviewId);
            navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/interviews/${newInterviewId}`);
          }}
        />
      )}

      {/* Create Behavioral Simulation Modal */}
      {showCreateBehavioralModal && (
        <CreateBehavioralTestModal
          isOpen={showCreateBehavioralModal}
          onClose={() => {
            setShowCreateBehavioralModal(false);
            setInitialBehavioralPersonaId(undefined);
          }}
          studyId={activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}
          initialPersonaId={initialBehavioralPersonaId}
          onTestCreated={(testId, runId) => {
            setActiveTestId(testId);
            setActiveRunId(runId);
            navigate(
              runId
                ? `/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/${testId}/runs/${runId}`
                : `/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/behavioral-tests/${testId}`
            );
          }}
        />
      )}

    </div>
  );
};
