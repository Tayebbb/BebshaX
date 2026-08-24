import React, { useState, useEffect } from 'react';
import {
  PenSquare,
  LayoutGrid,
  Contact2,
  Building2,
  ChevronDown,
  ChevronRight,
  PanelLeft,
  MessageCircle,
  LogOut,
  ExternalLink,
  Sparkles,
  Zap,
  Globe,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { NewStudyView } from './views/NewStudyView';
import { StudiesDashboardView } from './views/StudiesDashboardView';
import { PersonaLibraryView } from './views/PersonaLibraryView';
import { StudyWorkflowView } from './views/StudyWorkflowView';
import { OrganisationView } from './views/OrganisationView';
import { StudyType, Study } from '../../types';
import { api } from '../../services/api';

export type DashboardTab = 'new-study' | 'dashboard' | 'personas' | 'organisation' | 'study-workflow';

interface DashboardLayoutProps {
  onOpenLandingPage?: () => void;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({ onOpenLandingPage }) => {
  const { user, logout } = useAuth();
  const { currentPath, navigate } = useNavigation();

  const [activeTab, setActiveTab] = useState<DashboardTab>(() => {
    if (currentPath.includes('/personas')) return 'personas';
    if (currentPath.includes('/organisation')) return 'organisation';
    if (currentPath.includes('/new-study')) return 'new-study';
    if (currentPath.includes('/study')) return 'study-workflow';
    return 'new-study';
  });

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isRecentStudiesOpen, setIsRecentStudiesOpen] = useState(true);
  const [recentStudies, setRecentStudies] = useState<Study[]>([]);
  const [activeStudyId, setActiveStudyId] = useState<string | undefined>(undefined);
  const [initialWorkflowType, setInitialWorkflowType] = useState<StudyType>('interviews');
  const [initialWorkflowPrompt, setInitialWorkflowPrompt] = useState<string | undefined>(undefined);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showAssistantModal, setShowAssistantModal] = useState(false);

  useEffect(() => {
    const loadRecent = async () => {
      try {
        const data = await api.getStudies();
        setRecentStudies(data.slice(0, 5));
      } catch {
        // fallback
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

  const displayName = user?.full_name?.split(' ')[0]?.toUpperCase() || 'SAIDUL';

  const handleStartStudy = (type: StudyType, prompt?: string) => {
    setInitialWorkflowType(type);
    setInitialWorkflowPrompt(prompt);
    setActiveStudyId(undefined);
    setActiveTab('study-workflow');
  };

  const handleOpenStudy = (studyId: string) => {
    setActiveStudyId(studyId);
    setActiveTab('study-workflow');
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
      id: 'organisation' as DashboardTab,
      label: 'Organisation',
      icon: <Building2 size={16} />,
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
            {!isSidebarCollapsed && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                }}
                onClick={() => setActiveTab('new-study')}
              >
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '6px',
                    background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#080909',
                    fontWeight: 800,
                    fontSize: '0.85rem',
                  }}
                >
                  B
                </div>
                <span
                  style={{
                    fontSize: '1.15rem',
                    fontWeight: 700,
                    letterSpacing: '-0.02em',
                    color: '#FFFFFF',
                  }}
                >
                  BebshaX
                </span>
              </div>
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
                  onClick={() => {
                    setActiveTab(item.id);
                    if (item.id === 'study-workflow') {
                      setActiveStudyId(undefined);
                    }
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    justifyContent: isSidebarCollapsed ? 'center' : 'flex-start',
                    width: '100%',
                    padding: isSidebarCollapsed ? '10px 0' : '10px 12px',
                    borderRadius: '10px',
                    background: isActive ? 'rgba(246, 200, 120, 0.12)' : 'transparent',
                    color: isActive ? '#F6C878' : '#9CA3AF',
                    border: 'none',
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
                      e.currentTarget.style.color = '#9CA3AF';
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span style={{ color: isActive ? '#F6C878' : '#8A909A' }}>{item.icon}</span>
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
                  color: '#6B7280',
                  cursor: 'pointer',
                  marginBottom: '6px',
                }}
              >
                <span>Recent Studies</span>
                {isRecentStudiesOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </div>

              {isRecentStudiesOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', paddingLeft: '4px' }}>
                  {recentStudies.map((st) => {
                    const isCompleted = st.status === 'completed';
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
                          color: '#9CA3AF',
                          cursor: 'pointer',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          transition: 'color 0.16s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.color = '#FFFFFF';
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.color = '#9CA3AF';
                          e.currentTarget.style.background = 'transparent';
                        }}
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
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{st.title}</span>
                      </div>
                    );
                  })}

                  <div
                    onClick={() => setActiveTab('dashboard')}
                    style={{
                      fontSize: '0.78rem',
                      color: '#F6C878',
                      fontWeight: 600,
                      padding: '6px 8px',
                      cursor: 'pointer',
                    }}
                  >
                    See more
                  </div>
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
              padding: isSidebarCollapsed ? '8px 0' : '8px 10px',
              borderRadius: '12px',
              background: 'rgba(255, 255, 255, 0.025)',
              border: '1px solid rgba(255, 255, 255, 0.06)',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {/* User Avatar */}
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #EF4444 0%, #B91C1C 100%)',
                  color: '#FFFFFF',
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {displayName.charAt(0)}
              </div>

              {!isSidebarCollapsed && (
                <span
                  style={{
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    color: '#FFFFFF',
                    letterSpacing: '0.02em',
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
                  fontWeight: 700,
                  color: '#F6C878',
                  background: 'rgba(246, 200, 120, 0.12)',
                  border: '1px solid rgba(246, 200, 120, 0.25)',
                  padding: '2px 6px',
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
                width: isSidebarCollapsed ? '180px' : '100%',
                background: '#121315',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '12px',
                padding: '6px',
                boxShadow: '0 12px 30px rgba(0, 0, 0, 0.6)',
                zIndex: 50,
              }}
            >
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
                    color: '#FFFFFF',
                    fontSize: '0.82rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    borderRadius: '8px',
                  }}
                >
                  <Globe size={14} /> Marketing Site
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  setShowUserMenu(false);
                  logout();
                }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 10px',
                  background: 'transparent',
                  border: 'none',
                  color: '#EF4444',
                  fontSize: '0.82rem',
                  textAlign: 'left',
                  cursor: 'pointer',
                  borderRadius: '8px',
                }}
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

            {/* Quick Status Pill */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.2)',
                  borderRadius: '20px',
                  padding: '4px 12px',
                  fontSize: '0.76rem',
                  color: '#10B981',
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10B981' }} />
                <span>FreeLLMpool • 222 Routes Active</span>
              </div>

              {onOpenLandingPage && (
                <button
                  type="button"
                  onClick={onOpenLandingPage}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: '#9CA3AF',
                    borderRadius: '8px',
                    padding: '4px 10px',
                    fontSize: '0.76rem',
                    cursor: 'pointer',
                  }}
                >
                  View Landing Page
                </button>
              )}
            </div>
          </header>
        )}

        {/* Tab View Switcher */}
        {activeTab === 'new-study' && (
          <NewStudyView onStartStudy={handleStartStudy} />
        )}

        {activeTab === 'dashboard' && (
          <StudiesDashboardView
            onCreateStudy={() => setActiveTab('new-study')}
            onOpenStudy={handleOpenStudy}
          />
        )}

        {activeTab === 'personas' && (
          <PersonaLibraryView
            onStartInterviewWithPersona={(pId) => {
              setActiveStudyId(undefined);
              setActiveTab('study-workflow');
            }}
          />
        )}

        {activeTab === 'organisation' && <OrganisationView />}

        {activeTab === 'study-workflow' && (
          <StudyWorkflowView
            studyId={activeStudyId}
            initialType={initialWorkflowType}
            initialPrompt={initialWorkflowPrompt}
            onExit={() => setActiveTab('dashboard')}
          />
        )}
      </main>

      {/* ============================================================
          FLOATING GOLD ASSISTANT BUBBLE (Bottom-right corner)
         ============================================================ */}
      <button
        type="button"
        aria-label="Ask BebshaX AI Assistant"
        onClick={() => setShowAssistantModal(true)}
        style={{
          position: 'fixed',
          bottom: '28px',
          right: '28px',
          width: '50px',
          height: '50px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
          color: '#080909',
          border: 'none',
          boxShadow: '0 8px 24px rgba(246, 200, 120, 0.35)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 50,
          transition: 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.08)')}
        onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
      >
        <MessageCircle size={24} fill="#080909" />
      </button>

      {/* Quick AI Assistant Guidance Modal */}
      {showAssistantModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'flex-end',
            padding: '24px',
            background: 'rgba(0, 0, 0, 0.5)',
          }}
          onClick={() => setShowAssistantModal(false)}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '380px',
              background: '#121315',
              border: '1px solid rgba(246, 200, 120, 0.35)',
              borderRadius: '20px',
              padding: '24px',
              boxShadow: '0 20px 48px rgba(0, 0, 0, 0.6)',
              marginBottom: '60px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <Sparkles size={18} color="#F6C878" />
              <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#FFFFFF', margin: 0 }}>
                BebshaX Research Assistant
              </h2>
            </div>
            <p style={{ fontSize: '0.84rem', color: '#9CA3AF', lineHeight: 1.5, margin: '0 0 16px 0' }}>
              How can I help you design your next study? You can test positioning, interview synthetic buyers, or simulate landing page friction.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                type="button"
                onClick={() => {
                  setShowAssistantModal(false);
                  handleStartStudy('interviews', 'Should we lead with pricing or with the product story?');
                }}
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#FFFFFF',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                "Should we lead with pricing or product story?"
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowAssistantModal(false);
                  handleStartStudy('landing_page_test', 'Test friction points on our checkout flow');
                }}
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  color: '#FFFFFF',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                "Test friction points on checkout flow"
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
