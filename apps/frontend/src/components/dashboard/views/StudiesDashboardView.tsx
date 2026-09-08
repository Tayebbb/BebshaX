import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import { findExampleStudy, EXAMPLE_STUDY_STEP } from '../../../utils/exampleStudy';
import './studies.css';

interface StudiesDashboardViewProps {
  onCreateStudy: () => void;
  onOpenStudy: (studyId: string, step?: number) => void;
}

const TYPE_LABELS: Record<string, string> = {
  landing_page_test: 'Landing Page Test',
  message_testing: 'Message Testing',
  ab_test: 'A/B Test',
  interviews: 'Interviews',
};

export const StudiesDashboardView: React.FC<StudiesDashboardViewProps> = ({
  onCreateStudy,
  onOpenStudy,
}) => {
  const [studies, setStudies] = useState<Study[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'completed' | 'in_progress'>('all');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Only one kebab menu is open at a time, so a single ref tracks it.
  const menuRef = useRef<HTMLDivElement>(null);

  const loadStudies = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.getStudies();
      setStudies(data);
      setLoadError(null);
    } catch (err: any) {
      // A failed fetch is not "you have no studies" — saying so would invite
      // the user to recreate work they already have.
      setLoadError(err?.message || 'Could not load your studies.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStudies();
  }, [loadStudies]);

  // An open kebab menu closes on Escape or any outside pointer press;
  // ArrowUp/ArrowDown cycle focus through its items (mirrors the user
  // popover in DashboardLayout).
  useEffect(() => {
    if (!activeMenuId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        setActiveMenuId(null);
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const items = Array.from(
          menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
        );
        if (items.length === 0) return;
        e.preventDefault();
        const idx = items.indexOf(document.activeElement as HTMLElement);
        const step = e.key === 'ArrowDown' ? 1 : -1;
        items[(idx + step + items.length) % items.length].focus();
      }
    };
    const onPress = () => setActiveMenuId(null);
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPress);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPress);
    };
  }, [activeMenuId]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await api.deleteStudy(id);
      setStudies((prev) => prev.filter((s) => s.id !== id));
      setActiveMenuId(null);
      // the focused row unmounts — keep keyboard users anchored in the list
      listRef.current?.focus();
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

  const demoStudy = findExampleStudy(studies);
  const regularStudies = filteredStudies.filter((s) => !s.is_demo);

  // The blurb may only name what the demo study actually carries: the report is
  // guaranteed by findExampleStudy, personas are not. (The study list never
  // serializes interviews, so they are never advertised.)
  const demoOffers = demoStudy
    ? [
        'a finished decision report',
        demoStudy.persona_count > 0
          ? `${demoStudy.persona_count} persona${demoStudy.persona_count === 1 ? '' : 's'}`
          : null,
      ].filter(Boolean)
    : [];

  // Honest totals derived from the loaded list only. "In flight" matches the
  // In Progress tab bucket (drafts included) so the two never disagree.
  const own = studies.filter((s) => !s.is_demo);
  const completedCount = own.filter((s) => s.status === 'completed').length;
  const inFlightCount = own.filter((s) => s.status === 'in_progress' || s.status === 'draft').length;
  const personaCount = own.reduce((sum, s) => sum + (s.persona_count || 0), 0);

  const rowStatus = (study: Study) => {
    if (study.status === 'completed') {
      return <span className="sd-status sd-status--completed"><span className="sd-status-dot" />COMPLETED</span>;
    }
    if (study.status === 'in_progress') {
      return <span className="sd-status sd-status--live"><span className="sd-status-dot" />IN FLIGHT</span>;
    }
    return <span className="sd-status sd-status--draft"><span className="sd-status-dot" />DRAFT</span>;
  };

  // Reopening a study drops the user where they left off (demo lands on its report).
  const openRow = (id: string) => {
    const study = studies.find((s) => s.id === id);
    onOpenStudy(id, study?.step || 1);
  };

  return (
    <div className="sd-root">
      <div className="sd-ambient" aria-hidden="true" />
      <div className="sd-content">
        <header>
          <div className="sd-kicker">Research Console</div>
          <div className="sd-hero-row">
            <h1 className="sd-display">
              Studies<span className="sd-dot" aria-hidden="true">.</span>
            </h1>
            <button type="button" className="sd-cta" onClick={onCreateStudy}>
              <Plus size={16} strokeWidth={2.5} />
              Create Study
            </button>
          </div>

          <div className="sd-metrics" role="group" aria-label="Research totals">
            <div>
              <div className="sd-metric-num">{own.length}</div>
              <div className="sd-metric-label">Studies</div>
            </div>
            <div>
              <div className="sd-metric-num"><em>{inFlightCount}</em></div>
              <div className="sd-metric-label">In Flight</div>
            </div>
            <div>
              <div className="sd-metric-num">{completedCount}</div>
              <div className="sd-metric-label">Completed</div>
            </div>
            <div>
              <div className="sd-metric-num">{personaCount}</div>
              <div className="sd-metric-label">Personas</div>
            </div>
          </div>
        </header>

        <div className="sd-toolbar">
          <div className="sd-search">
            <Search size={16} aria-hidden="true" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search your studies..."
              aria-label="Search your studies"
            />
          </div>

          <div className="sd-tabs" role="group" aria-label="Filter studies">
            {(['all', 'completed', 'in_progress'] as const).map((tab) => {
              const label = tab === 'all' ? 'All' : tab === 'completed' ? 'Completed' : 'In Progress';
              return (
                <button
                  key={tab}
                  type="button"
                  className="sd-tab"
                  aria-pressed={selectedFilter === tab}
                  onClick={() => setSelectedFilter(tab)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {demoStudy && (
          <div
            className="sd-demo"
            role="button"
            tabIndex={0}
            onClick={() => onOpenStudy(demoStudy.id, EXAMPLE_STUDY_STEP)}
            onKeyDown={(e) => {
              if (e.target !== e.currentTarget) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onOpenStudy(demoStudy.id, EXAMPLE_STUDY_STEP);
              }
            }}
          >
            <div>
              <div className="sd-demo-title">
                {demoStudy.title}
                <span className="sd-demo-badge">DEMO STUDY</span>
              </div>
              <div className="sd-demo-sub">
                Sample study — explore {demoOffers.join(', ')}
              </div>
            </div>
            <div className="sd-demo-open">
              Explore Report
              <ArrowUpRight size={16} />
            </div>
          </div>
        )}

        <div className="sd-label">Your Studies</div>

        {/* Loading and error states live outside the list: a role="list"
            only admits listitem children, so an alert or busy region placed
            inside it is pruned from the accessibility tree. */}
        {isLoading ? (
          // Showing "start your first study" to someone who already has
          // studies is a lie, so the skeleton owns the pre-fetch frame.
          <div className="sd-loading" role="status" aria-busy="true" aria-live="polite" aria-label="Loading your studies">
            {[0, 1, 2].map((i) => (
              <div key={i} className="bx-skeleton sd-loading-row" />
            ))}
          </div>
        ) : loadError ? (
          <div className="sd-empty" role="alert">
            <div className="sd-empty-kicker">Could Not Load Studies</div>
            <div className="sd-empty-line">Your studies are still there — this view could not reach them.</div>
            <div className="sd-empty-sub">{loadError}</div>
            <button type="button" className="sd-empty-cta" onClick={loadStudies}>
              Retry
            </button>
          </div>
        ) : (
          <div className="sd-list" role="list" ref={listRef} tabIndex={-1}>
            {regularStudies.length === 0 ? (
            <div className="sd-empty">
              <div className="sd-empty-kicker">Nothing In Flight</div>
              <div className="sd-empty-line">
                {searchQuery || selectedFilter !== 'all'
                  ? 'No studies match your filter.'
                  : 'Your first study starts with a question.'}
              </div>
              <div className="sd-empty-sub">
                {searchQuery || selectedFilter !== 'all'
                  ? 'Try a different name or status, or clear the filters.'
                  : 'Describe a business idea and interview synthetic personas about it.'}
              </div>
              <button type="button" className="sd-empty-cta" onClick={onCreateStudy}>
                <Plus size={15} strokeWidth={2.5} />
                Start your first study
              </button>
            </div>
          ) : (
            regularStudies.map((study, index) => {
              const isMenuOpen = activeMenuId === study.id;
              return (
                <div
                  key={study.id}
                  className="sd-row"
                  style={{ '--sd-i': Math.min(index, 12) } as React.CSSProperties}
                  role="listitem"
                  onClick={() => openRow(study.id)}
                >
                  <div>
                    {/* The title is the row's real keyboard control — the row
                        click is a pointer-only enhancement. */}
                    <button
                      type="button"
                      className="sd-row-titlebtn"
                      onClick={(e) => {
                        e.stopPropagation();
                        openRow(study.id);
                      }}
                    >
                      {study.title}
                    </button>
                    <div className="sd-row-meta">
                      {study.duration_text ||
                        (study.persona_count > 0
                          ? `${study.persona_count} personas`
                          : 'Just created • No personas yet')}
                    </div>
                  </div>

                  <div className="sd-row-right">
                    {rowStatus(study)}
                    <div className="sd-row-type">{TYPE_LABELS[study.type] ?? study.type}</div>
                    <span className="sd-row-open" aria-hidden="true">
                      Open
                      <ArrowUpRight size={14} />
                    </span>

                    <div className="sd-menu-wrap" onPointerDown={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="sd-menu-btn"
                        aria-label="Study options"
                        aria-expanded={isMenuOpen}
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveMenuId(isMenuOpen ? null : study.id);
                        }}
                      >
                        <MoreVertical size={16} />
                      </button>

                      {isMenuOpen && (
                        <div className="sd-menu" role="menu" aria-label="Study options" ref={menuRef}>
                          <button
                            type="button"
                            role="menuitem"
                            className="sd-menu-item"
                            onClick={(e) => {
                              e.stopPropagation();
                              openRow(study.id);
                            }}
                          >
                            <FileText size={14} /> View Study
                          </button>
                          <button
                            type="button"
                            role="menuitem"
                            className="sd-menu-item sd-menu-item--danger"
                            onClick={(e) => handleDelete(e, study.id)}
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
        )}
      </div>
    </div>
  );
};
