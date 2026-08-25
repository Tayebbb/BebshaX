import React, { useState, useEffect } from 'react';
import {
  Search,
  Plus,
  MoreVertical,
  ArrowUpRight,
  FileText,
  Trash2,
} from 'lucide-react';
import { Study } from '../../../types';
import { api } from '../../../services/api';

interface StudiesDashboardViewProps {
  onCreateStudy: () => void;
  onOpenStudy: (studyId: string) => void;
}

export const StudiesDashboardView: React.FC<StudiesDashboardViewProps> = ({
  onCreateStudy,
  onOpenStudy,
}) => {
  const [studies, setStudies] = useState<Study[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'completed' | 'in_progress'>('all');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  useEffect(() => {
    const loadStudies = async () => {
      try {
        const data = await api.getStudies();
        setStudies(data);
      } catch {
        // fallback
      }
    };
    loadStudies();
  }, []);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.deleteStudy(id);
      setStudies((prev) => prev.filter((s) => s.id !== id));
      setActiveMenuId(null);
    } catch {
      // ignore
    }
  };

  const filteredStudies = studies.filter((study) => {
    const matchesSearch =
      study.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (study.prompt && study.prompt.toLowerCase().includes(searchQuery.toLowerCase()));

    if (!matchesSearch) return false;
    if (selectedFilter === 'completed') return study.status === 'completed';
    if (selectedFilter === 'in_progress') return study.status === 'in_progress' || study.status === 'draft';
    return true;
  });

  const demoStudy = studies.find((s) => s.is_demo);
  const regularStudies = filteredStudies.filter((s) => !s.is_demo);

  const formatTypeLabel = (type: string) => {
    switch (type) {
      case 'landing_page_test':
        return 'Landing Page Test';
      case 'message_testing':
        return 'Message Testing';
      case 'ab_test':
        return 'A/B Test';
      case 'interviews':
      default:
        return 'Interviews';
    }
  };

  return (
    <div
      style={{
        padding: '32px 40px',
        maxWidth: '1200px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* Main Studies Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
        }}
      >
        <h1
          style={{
            fontSize: '1.75rem',
            fontWeight: 600,
            color: '#FFFFFF',
            letterSpacing: '-0.02em',
            margin: 0,
          }}
        >
          Studies
        </h1>

        <button
          type="button"
          onClick={onCreateStudy}
          style={{
            background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '10px',
            padding: '9px 18px',
            fontSize: '0.86rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: 'pointer',
            boxShadow: '0 4px 14px rgba(99, 102, 241, 0.35)',
            transition: 'transform 0.18s ease, box-shadow 0.18s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-1px)';
            e.currentTarget.style.boxShadow = '0 6px 20px rgba(99, 102, 241, 0.5)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 4px 14px rgba(99, 102, 241, 0.35)';
          }}
        >
          <Plus size={16} strokeWidth={2.5} />
          Create Study
        </button>
      </div>

      {/* Search & Filter Tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        {/* Search Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '12px',
            padding: '8px 14px',
            width: '320px',
          }}
        >
          <Search size={16} color="#6B7280" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search your studies..."
            style={{
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: '#FFFFFF',
              fontSize: '0.86rem',
              width: '100%',
            }}
          />
        </div>

        {/* Tabs Filter */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'rgba(255, 255, 255, 0.025)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            borderRadius: '10px',
            padding: '4px',
          }}
        >
          {(['all', 'completed', 'in_progress'] as const).map((tab) => {
            const isTabActive = selectedFilter === tab;
            const label =
              tab === 'all' ? 'All' : tab === 'completed' ? 'Completed' : 'In Progress';
            return (
              <button
                key={tab}
                type="button"
                onClick={() => setSelectedFilter(tab)}
                style={{
                  background: isTabActive ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                  color: isTabActive ? '#818CF8' : '#8A909A',
                  border: isTabActive ? '1px solid rgba(99, 102, 241, 0.3)' : '1px solid transparent',
                  borderRadius: '7px',
                  padding: '6px 14px',
                  fontSize: '0.8rem',
                  fontWeight: isTabActive ? 600 : 400,
                  cursor: 'pointer',
                  transition: 'all 0.18s ease',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Featured Demo Study Card */}
      {demoStudy && (
        <div
          onClick={() => onOpenStudy(demoStudy.id)}
          style={{
            background:
              'linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(18, 21, 28, 0.85) 100%)',
            border: '1px solid rgba(99, 102, 241, 0.35)',
            borderRadius: '16px',
            padding: '20px 24px',
            marginBottom: '28px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            transition: 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.6)';
            e.currentTarget.style.transform = 'translateY(-2px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.35)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                background: 'rgba(99, 102, 241, 0.15)',
                color: '#818CF8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Plus size={18} strokeWidth={2.5} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span
                  style={{
                    fontSize: '1rem',
                    fontWeight: 600,
                    color: '#818CF8',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {demoStudy.title}
                </span>
                <span
                  style={{
                    fontSize: '0.68rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    padding: '2px 8px',
                    borderRadius: '6px',
                    background: 'rgba(99, 102, 241, 0.15)',
                    color: '#818CF8',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                  }}
                >
                  DEMO STUDY
                </span>
              </div>
              <div style={{ fontSize: '0.82rem', color: '#9CA3AF', marginTop: '2px' }}>
                Sample study — explore a finished report and pre-generated interviews
              </div>
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              color: '#818CF8',
              fontSize: '0.84rem',
              fontWeight: 600,
            }}
          >
            <span>Explore Report</span>
            <ArrowUpRight size={16} />
          </div>
        </div>
      )}

      {/* YOUR STUDIES Subtitle */}
      <div
        style={{
          fontSize: '0.74rem',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: '#6B7280',
          marginBottom: '14px',
        }}
      >
        Your Studies
      </div>

      {/* Studies List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {regularStudies.length === 0 ? (
          <div
            style={{
              padding: '48px',
              textAlign: 'center',
              background: 'rgba(255, 255, 255, 0.015)',
              border: '1px dashed rgba(255, 255, 255, 0.1)',
              borderRadius: '16px',
              color: '#8A909A',
            }}
          >
            No studies matching your search. Click "+ Create Study" to start your first research study.
          </div>
        ) : (
          regularStudies.map((study) => {
            const isCompleted = study.status === 'completed';
            const isMenuOpen = activeMenuId === study.id;

            return (
              <div
                key={study.id}
                onClick={() => onOpenStudy(study.id)}
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: '14px',
                  padding: '18px 22px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '16px',
                  transition: 'all 0.18s cubic-bezier(0.16, 1, 0.3, 1)',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.35)';
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.035)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)';
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)';
                }}
              >
                {/* Left info */}
                <div>
                  <div
                    style={{
                      fontSize: '0.98rem',
                      fontWeight: 600,
                      color: '#FFFFFF',
                      letterSpacing: '-0.01em',
                      marginBottom: '4px',
                    }}
                  >
                    {study.title}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#8A909A' }}>
                    {study.duration_text ||
                      (study.persona_count > 0
                        ? `${study.persona_count} personas`
                        : 'Just created • No personas yet')}
                  </div>
                </div>

                {/* Right badges & Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                  {/* Status Badge */}
                  {isCompleted ? (
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        color: '#10B981',
                        fontSize: '0.76rem',
                        fontWeight: 700,
                        letterSpacing: '0.04em',
                      }}
                    >
                      <span>COMPLETED</span>
                      <div style={{ display: 'flex', gap: '3px' }}>
                        <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#10B981' }} />
                        <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#10B981' }} />
                        <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#10B981' }} />
                        <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: '#10B981' }} />
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        fontSize: '0.74rem',
                        fontWeight: 600,
                        letterSpacing: '0.04em',
                        color: '#9CA3AF',
                      }}
                    >
                      DRAFT
                    </div>
                  )}

                  {/* Study Type */}
                  <div
                    style={{
                      fontSize: '0.82rem',
                      color: '#D1D5DB',
                      minWidth: '110px',
                      textAlign: 'right',
                    }}
                  >
                    {formatTypeLabel(study.type)}
                  </div>

                  {/* Options Menu Button */}
                  <div style={{ position: 'relative' }}>
                    <button
                      type="button"
                      aria-label="Study options"
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveMenuId(isMenuOpen ? null : study.id);
                      }}
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
                      <MoreVertical size={16} />
                    </button>

                    {isMenuOpen && (
                      <div
                        style={{
                          position: 'absolute',
                          right: 0,
                          top: '100%',
                          marginTop: '6px',
                          background: '#131415',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '10px',
                          padding: '6px',
                          minWidth: '140px',
                          zIndex: 20,
                          boxShadow: '0 10px 25px rgba(0, 0, 0, 0.5)',
                        }}
                      >
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenStudy(study.id);
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
                            fontSize: '0.8rem',
                            textAlign: 'left',
                            cursor: 'pointer',
                            borderRadius: '6px',
                          }}
                        >
                          <FileText size={14} /> View Study
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDelete(e, study.id)}
                          style={{
                            width: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px 10px',
                            background: 'transparent',
                            border: 'none',
                            color: '#EF4444',
                            fontSize: '0.8rem',
                            textAlign: 'left',
                            cursor: 'pointer',
                            borderRadius: '6px',
                          }}
                        >
                          <Trash2 size={14} /> Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer subtle text */}
      <div
        style={{
          textAlign: 'center',
          marginTop: '36px',
          fontSize: '0.78rem',
          color: '#4B5563',
        }}
      >
        No more studies
      </div>
    </div>
  );
};
