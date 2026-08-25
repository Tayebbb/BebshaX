import React, { useState, useEffect } from 'react';
import {
  PenSquare,
  LayoutGrid,
  Contact2,
  Database,
  ChevronDown,
  ChevronRight,
  PanelLeft,
  LogOut,
  Globe,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { NewStudyView } from './views/NewStudyView';
import { StudiesDashboardView } from './views/StudiesDashboardView';
import { PersonaLibraryView } from './views/PersonaLibraryView';
import { StudyWorkflowView } from './views/StudyWorkflowView';
import { ModelRouterView } from './views/ModelRouterView';
import { DatasetSourcesView } from './views/DatasetSourcesView';
import { EvidenceLaboratoryView } from './views/EvidenceLaboratoryView';
import { SegmentationView } from './views/SegmentationView';
import { StudyType, Study } from '../../types';
import { api } from '../../services/api';
import { BebshaXLogo } from '../common/BebshaXLogo';

export type DashboardTab = 'new-study' | 'dashboard' | 'personas' | 'datasets' | 'router' | 'study-workflow' | 'evidence' | 'segmentation';

interface DashboardLayoutProps {
  onOpenLandingPage?: () => void;
}

const parseDashboardPath = (path: string): {
  tab: DashboardTab;
  studyId?: string;
  step?: number;
} => {
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
    return { tab: 'datasets' };
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

  const initialParsed = parseDashboardPath(currentPath);
  const [activeTab, setActiveTab] = useState<DashboardTab>(initialParsed.tab);
  const [activeStudyId, setActiveStudyId] = useState<string | undefined>(initialParsed.studyId);
  const [activeStep, setActiveStep] = useState<number>(initialParsed.step || 1);

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isRecentStudiesOpen, setIsRecentStudiesOpen] = useState(true);
  const [recentStudies, setRecentStudies] = useState<Study[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [initialWorkflowType, setInitialWorkflowType] = useState<StudyType>('interviews');
  const [initialWorkflowPrompt, setInitialWorkflowPrompt] = useState<string | undefined>(undefined);
  const [showUserMenu, setShowUserMenu] = useState(false);

  useEffect(() => {
    const parsed = parseDashboardPath(currentPath);
    setActiveTab(parsed.tab);
    if (parsed.studyId) {
      setActiveStudyId(parsed.studyId);
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
    else if (tab === 'datasets') navigate('/datasets');
    else if (tab === 'router') navigate('/router');
    else if (tab === 'study-workflow') navigate(`/research/${activeStudyId || 'tj6FY3cXDO8oxpuxeAMb'}/step1`);
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
      id: 'datasets' as DashboardTab,
      label: 'Dataset Sources',
      icon: <Database size={16} />,
    },
  ];

  return (
    <div
      style={{
        display: 'flex',
        minHeight: '100vh',
        background: '#080909',
        color: '#FFFFFF',
        position: 'relative',
        overflowX: 'hidden',
      }}
    >
      {/* ============================================================
          LEFT SIDEBAR (Matches Screenshots 1, 2, 3, 4)
         ============================================================ */}
      <aside
        style={{
          width: isSidebarCollapsed ? '72px' : '240px',
          background: '#080909',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
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
        {/* Top Brand Header */}
        <div>
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
                color: '#6B7280',
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
                    background: isActive ? 'rgba(20, 184, 166, 0.12)' : 'transparent',
                    color: isActive ? '#22D3EE' : '#8D9999',
                    border: isActive ? '1px solid rgba(20, 184, 166, 0.28)' : '1px solid transparent',
                    fontSize: '0.86rem',
                    fontWeight: isActive ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'all 0.18s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = '#FFFFFF';
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color = '#8D9999';
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span style={{ color: isActive ? '#14B8A6' : '#8D9999' }}>{item.icon}</span>
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
                  color: '#8D9999',
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
                      <div style={{ height: '14px', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.06)' }} />
                      <div style={{ height: '14px', width: '75%', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.06)' }} />
                      <div style={{ height: '14px', width: '60%', borderRadius: '4px', background: 'rgba(255, 255, 255, 0.06)' }} />
                    </div>
                  ) : recentStudies.length === 0 ? (
                    <div style={{ padding: '8px 10px', fontSize: '0.78rem', color: '#8D9999', lineHeight: 1.45 }}>
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
                              color: '#8D9999',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              transition: 'color 0.16s ease',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.color = '#FFFFFF';
                              e.currentTarget.style.background = '#111616';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.color = '#8D9999';
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
                                  background: '#10B981',
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
                          color: '#22D3EE',
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
          <div
            onClick={() => setShowUserMenu(!showUserMenu)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
              padding: isSidebarCollapsed ? '8px 0' : '8px 12px',
              borderRadius: '12px',
              background: showUserMenu ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.03)',
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
                    color: '#FFFFFF',
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
                    color: '#FFFFFF',
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
                  color: '#F6C878',
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
                  borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
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
                      background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                      color: '#080909',
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
                      color: '#FFFFFF',
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
                      color: '#9CA3AF',
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
                    color: '#FFFFFF',
                    fontSize: '0.82rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    borderRadius: '8px',
                    transition: 'background 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)')}
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
                color: '#E5E7EB',
                fontWeight: 500,
                letterSpacing: '-0.01em',
              }}
            >
              {getGreeting()}, {displayName}
            </div>
          </header>
        )}

        {/* Tab View Switcher */}
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
            onStartInterviewWithPersona={(pId) => {
              handleStartStudy('interviews', `Interview with persona ${pId}`);
            }}
          />
        )}

        {activeTab === 'datasets' && <DatasetSourcesView />}

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
              onNavigateToDatasets={() => navigate(`/datasets`)}
              onProceedToPersonas={(segmentId) => {
                navigate(`/research/${activeStudyId || 'study_default'}/step3`);
              }}
            />
          </div>
        )}
      </main>

    </div>
  );
};
