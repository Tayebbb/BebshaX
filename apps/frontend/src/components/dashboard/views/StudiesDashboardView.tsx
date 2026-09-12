import React, { useState, useEffect, useCallback, useRef, useLayoutEffect, useId } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Search,
  Plus,
  MoreVertical,
  ArrowUpRight,
  FileText,
  Trash2,
  AlertCircle,
  RotateCcw,
} from 'lucide-react';
import { Study } from '../../../types';
import { api } from '../../../services/api';
import { useRouteReady } from '../../../performance/routeTiming';
import { findExampleStudy, EXAMPLE_STUDY_STEP } from '../../../utils/exampleStudy';
import { Button } from '../../ui/Button';
import './studies.css';

interface StudiesDashboardViewProps {
  onCreateStudy: () => void;
  onOpenStudy: (studyId: string, step?: number) => void;
}

const TYPE_LABELS: Record<string, string> = {
  landing_page_test: 'Concept & Demand',
  message_testing: 'Message Testing',
  ab_test: 'Pricing & WTP',
  interviews: 'User Interviews',
};

export const StudiesDashboardView: React.FC<StudiesDashboardViewProps> = ({
  onCreateStudy,
  onOpenStudy,
}) => {
  const [studies, setStudies] = useState<Study[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  useRouteReady(!isLoading, loadError ? 'error' : studies.length ? 'content' : 'empty');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'completed' | 'in_progress'>('all');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Study | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const menuId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const menuInitialFocus = useRef<'first' | 'last'>('first');
  const cancelRef = useRef<HTMLButtonElement>(null);
  const requestRef = useRef({ active: false, loadId: 0, deleting: false });

  useLayoutEffect(() => {
    const epoch = { active: true, loadId: 0, deleting: false };
    requestRef.current = epoch;
    return () => { epoch.active = false; };
  }, []);

  const loadStudies = useCallback(async () => {
    const epoch = requestRef.current;
    const loadId = ++epoch.loadId;
    setIsLoading(true);
    try {
      const data = await api.getStudies();
      if (!epoch.active || epoch.loadId !== loadId) return;
      setStudies(data);
      setLoadError(null);
    } catch (error) {
      if (epoch.active && epoch.loadId === loadId) {
        setLoadError(error instanceof Error ? error.message : 'Could not load your studies.');
      }
    } finally {
      if (epoch.active && epoch.loadId === loadId) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStudies();
  }, [loadStudies]);

  useEffect(() => {
    if (!activeMenuId) return;
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
    items[menuInitialFocus.current === 'last' ? items.length - 1 : 0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setActiveMenuId(null);
        menuTriggerRef.current?.focus();
        return;
      }
      if (!menuRef.current?.contains(document.activeElement)) return;
      if (event.key === 'Tab') {
        setActiveMenuId(null);
        menuTriggerRef.current?.focus();
        return;
      }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) && items.length) {
        event.preventDefault();
        const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
        const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[nextIndex]?.focus();
      }
    };
    const onPress = (event: PointerEvent) => {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)
        && !menuTriggerRef.current?.contains(event.target)) setActiveMenuId(null);
    };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onPress);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onPress);
    };
  }, [activeMenuId]);

  const closeDelete = () => {
    if (requestRef.current.deleting) return;
    setPendingDelete(null);
    setDeleteError(null);
  };

  const handleDelete = async () => {
    const epoch = requestRef.current;
    if (!pendingDelete || !epoch.active || epoch.deleting) return;
    epoch.deleting = true;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      const deleted = await api.deleteStudy(pendingDelete.id);
      if (!epoch.active) return;
      if (!deleted) throw new Error('Deletion was not confirmed. Please try again.');
      setStudies((previous) => previous.filter((study) => study.id !== pendingDelete.id));
      setPendingDelete(null);
    } catch (error) {
      if (epoch.active) {
        const detail = error instanceof Error ? error.message : 'Please try again.';
        setDeleteError(`Could not delete this study. ${detail}`);
      }
    } finally {
      epoch.deleting = false;
      if (epoch.active) setIsDeleting(false);
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

  const demoOffers = demoStudy
    ? [
        'a finished decision report',
        demoStudy.persona_count > 0
          ? `${demoStudy.persona_count} synthetic persona${demoStudy.persona_count === 1 ? '' : 's'}`
          : null,
      ].filter(Boolean)
    : [];

  const own = studies.filter((s) => !s.is_demo);
  const completedCount = own.filter((s) => s.status === 'completed').length;
  const inFlightCount = own.filter((s) => s.status === 'in_progress' || s.status === 'draft').length;
  const personaCount = own.reduce((sum, s) => sum + (s.persona_count || 0), 0);

  const rowStatus = (study: Study) => {
    if (study.status === 'completed') {
      return <span className="sd-status sd-status--completed">Completed</span>;
    }
    if (study.status === 'in_progress') {
      return <span className="sd-status sd-status--live">In progress</span>;
    }
    return <span className="sd-status sd-status--draft">Draft</span>;
  };

  const openRow = (id: string) => {
    const study = studies.find((s) => s.id === id);
    onOpenStudy(id, study?.step || 1);
  };

  return (
    <div className="sd-root">
      <div className="sd-content">
        <header>
          <div className="sd-header-row">
            <div>
              <h1 className="sd-display">Studies</h1>
              <p className="sd-sub">Your synthetic research workspace.</p>
            </div>
            <Button variant="primary" className="sd-cta" onClick={onCreateStudy} leadingIcon={<Plus size={16} aria-hidden="true" />}>
              Create Study
            </Button>
          </div>

          <dl className="sd-metrics" aria-label="Research totals">
            {[
              { label: 'Studies', value: own.length },
              { label: 'In progress', value: inFlightCount },
              { label: 'Completed', value: completedCount },
              { label: 'Synthetic personas', value: personaCount },
            ].map(({ label, value }) => (
              <div key={label}>
                <dt className="sd-metric-label">{label}</dt>
                <dd className="sd-metric-num" aria-label={isLoading ? 'Loading' : loadError ? 'Unavailable' : undefined}>
                  {isLoading || loadError ? '-' : value}
                </dd>
              </div>
            ))}
          </dl>
        </header>

        <div className="sd-toolbar">
          <div className="sd-search">
            <Search size={16} aria-hidden="true" />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => { setSearchQuery(event.target.value); setActiveMenuId(null); }}
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
                  onClick={() => { setSelectedFilter(tab); setActiveMenuId(null); }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {demoStudy && (
          <button
            type="button"
            className="sd-demo"
            onClick={() => onOpenStudy(demoStudy.id, EXAMPLE_STUDY_STEP)}
          >
            <span>
              <span className="sd-demo-title">
                {demoStudy.title}
                <span className="sd-demo-badge">DEMO STUDY</span>
              </span>
              <span className="sd-demo-sub">Public example with {demoOffers.join(', ')}</span>
            </span>
            <span className="sd-demo-open">
              Explore Report
              <ArrowUpRight size={16} aria-hidden="true" />
            </span>
          </button>
        )}

        <h2 className="sd-label">Your Studies</h2>

        {isLoading ? (
          <div className="sd-loading" role="status" aria-busy="true" aria-live="polite" aria-label="Loading your studies">
            <span>Loading your studies...</span>
            {[0, 1, 2].map((index) => <div key={index} className="sd-loading-row" aria-hidden="true" />)}
          </div>
        ) : loadError ? (
          <div className="sd-empty" role="alert">
            <AlertCircle size={22} aria-hidden="true" />
            <h3 className="sd-empty-line">Could not load studies</h3>
            <p className="sd-empty-sub">{loadError}</p>
            <Button className="sd-empty-cta" onClick={() => { void loadStudies(); }} leadingIcon={<RotateCcw size={15} aria-hidden="true" />}>Retry</Button>
          </div>
        ) : (
          <div className="sd-workarea" ref={listRef} tabIndex={-1}>
          {regularStudies.length === 0 ? (
            <div className="sd-empty">
              <FileText size={24} aria-hidden="true" />
              <h3 className="sd-empty-line">
                {searchQuery || selectedFilter !== 'all'
                  ? 'No studies match your filter.'
                  : 'Your first study starts with a question.'}
              </h3>
              <p className="sd-empty-sub">
                {searchQuery || selectedFilter !== 'all'
                  ? 'No results for the current search and status.'
                  : 'No saved studies yet.'}
              </p>
              {searchQuery || selectedFilter !== 'all' ? (
                <Button className="sd-empty-cta" onClick={() => { setSearchQuery(''); setSelectedFilter('all'); }} leadingIcon={<RotateCcw size={15} aria-hidden="true" />}>Clear filters</Button>
              ) : (
                <Button className="sd-empty-cta" onClick={onCreateStudy} leadingIcon={<Plus size={15} aria-hidden="true" />}>Start your first study</Button>
              )}
            </div>
          ) : (
            <div className="sd-list" role="list" aria-label="Your studies">
            {regularStudies.map((study) => {
              const isMenuOpen = activeMenuId === study.id;
              return (
                <div key={study.id} className="sd-row" role="listitem">
                  <div className="sd-row-main">
                    <button type="button" className="sd-row-titlebtn" onClick={() => openRow(study.id)}>
                      {study.title}
                      <ArrowUpRight size={15} aria-hidden="true" />
                    </button>
                    <div className="sd-row-meta">
                      {study.duration_text ||
                        (study.persona_count > 0
                          ? `${study.persona_count} synthetic persona${study.persona_count === 1 ? '' : 's'}`
                          : 'No personas yet')}
                      {study.step ? <span>Step {study.step}</span> : null}
                    </div>
                  </div>

                  <div className="sd-row-right">
                    {rowStatus(study)}
                    <div className="sd-row-type">{TYPE_LABELS[study.type] ?? study.type}</div>

                    <div className="sd-menu-wrap">
                      <Button
                        icon
                        variant="ghost"
                        className="sd-menu-btn"
                        aria-label="Study options"
                        title="Study options"
                        aria-haspopup="menu"
                        aria-controls={isMenuOpen ? menuId : undefined}
                        aria-expanded={isMenuOpen}
                        onClick={(event) => {
                          menuTriggerRef.current = event.currentTarget;
                          menuInitialFocus.current = 'first';
                          setActiveMenuId(isMenuOpen ? null : study.id);
                        }}
                        onKeyDown={(event) => {
                          if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
                          event.preventDefault();
                          menuTriggerRef.current = event.currentTarget;
                          menuInitialFocus.current = event.key === 'ArrowUp' ? 'last' : 'first';
                          setActiveMenuId(study.id);
                        }}
                      >
                        <MoreVertical size={17} aria-hidden="true" />
                      </Button>

                      {isMenuOpen && (
                        <div id={menuId} className="sd-menu" role="menu" aria-label="Study options" ref={menuRef}>
                          <button
                            type="button"
                            role="menuitem"
                            tabIndex={-1}
                            className="sd-menu-item"
                            onClick={() => { setActiveMenuId(null); openRow(study.id); }}
                          >
                            <FileText size={15} aria-hidden="true" /> View Study
                          </button>
                          <button
                            type="button"
                            role="menuitem"
                            tabIndex={-1}
                            className="sd-menu-item sd-menu-item--danger"
                            onClick={() => {
                              setActiveMenuId(null);
                              setDeleteError(null);
                              setPendingDelete(study);
                            }}
                          >
                            <Trash2 size={15} aria-hidden="true" /> Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
          )}
          </div>
        )}
      </div>
      <Dialog.Root open={!!pendingDelete} onOpenChange={(open) => { if (!open) closeDelete(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="sd-dialog-overlay" />
          <Dialog.Content
            className="sd-dialog"
            aria-modal="true"
            onOpenAutoFocus={(event) => { event.preventDefault(); cancelRef.current?.focus(); }}
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              if (menuTriggerRef.current?.isConnected) menuTriggerRef.current.focus();
              else listRef.current?.focus();
            }}
            onEscapeKeyDown={(event) => { if (requestRef.current.deleting) event.preventDefault(); }}
            onInteractOutside={(event) => { if (requestRef.current.deleting) event.preventDefault(); }}
          >
            <Dialog.Title className="sd-dialog-title">Delete study?</Dialog.Title>
            <Dialog.Description className="sd-dialog-description">
              <strong>{pendingDelete?.title}</strong> will be permanently deleted. This cannot be undone.
            </Dialog.Description>
            {deleteError && <p className="sd-delete-error" role="alert"><AlertCircle size={17} aria-hidden="true" /><span>{deleteError}</span></p>}
            <div className="sd-dialog-actions">
              <Button ref={cancelRef} onClick={closeDelete} disabled={isDeleting}>Cancel</Button>
              <Button variant="danger" loading={isDeleting} aria-label="Delete study" onClick={() => { void handleDelete(); }} leadingIcon={<Trash2 size={16} aria-hidden="true" />}>
                {isDeleting ? 'Deleting...' : 'Delete study'}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
};
