import React, { useState, useEffect } from 'react';
import { api } from '../../../services/api';
import { DatasetSource, DatasetPersonaRun, DatasetPreviewResponse } from '../../../types/dataset';
import { DatasetCandidate } from '../../../types/evidence';
import { OpenRouterDiagnosticModal } from './OpenRouterDiagnosticModal';
import {
  Database,
  Plus,
  RefreshCw,
  Trash2,
  Link,
  Upload,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  X,
  Cpu,
  Table,
  ChevronLeft,
  ChevronRight,
  Bot,
  Download,
  Globe,
  ThumbsDown,
} from 'lucide-react';

interface DatasetSourcesViewProps {
  studyId?: string;
}

export const DatasetSourcesView: React.FC<DatasetSourcesViewProps> = ({ studyId }) => {
  const [datasets, setDatasets] = useState<DatasetSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDataset, setSelectedDataset] = useState<DatasetSource | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'preview' | 'schema' | 'stats' | 'quality' | 'segments'>('overview');

  // Main panel switcher: 'sources' = manually-managed datasets, 'discovered' = autonomous candidates
  const [mainTab, setMainTab] = useState<'sources' | 'discovered'>('sources');

  // Autonomous dataset candidates state
  const [candidates, setCandidates] = useState<DatasetCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [candidateActionMsg, setCandidateActionMsg] = useState<{ id: string; type: 'success' | 'error'; text: string } | null>(null);

  // Preview State
  const [previewData, setPreviewData] = useState<DatasetPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewOffset, setPreviewOffset] = useState(0);
  const PREVIEW_PAGE_SIZE = 15;

  // Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [addMode, setAddMode] = useState<'url' | 'upload'>('url');
  const [isGenerateModalOpen, setIsGenerateModalOpen] = useState(false);
  const [generatingDataset, setGeneratingDataset] = useState<DatasetSource | null>(null);
  const [isOpenRouterModalOpen, setIsOpenRouterModalOpen] = useState(false);

  // Form State
  const [datasetName, setDatasetName] = useState('');
  const [datasetUrl, setDatasetUrl] = useState('');
  const [datasetDesc, setDatasetDesc] = useState('');
  const [datasetType] = useState('csv');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Refresh Notification Feedback
  const [refreshNotification, setRefreshNotification] = useState<{ id: string; message: string; changed: boolean } | null>(null);

  // Persona Generation State
  const [personaCount, setPersonaCount] = useState(10);
  const [businessName, setBusinessName] = useState('BebshaX Market Validation');
  const [businessDesc, setBusinessDesc] = useState('Evidence-grounded user demand testing');
  const [generating, setGenerating] = useState(false);
  const [generationRun, setGenerationRun] = useState<DatasetPersonaRun | null>(null);

  useEffect(() => {
    loadDatasets();
    if (studyId) loadCandidates();
  }, [studyId]);

  useEffect(() => {
    if (selectedDataset && activeTab === 'preview') {
      loadPreview(selectedDataset.id, 0);
    }
  }, [selectedDataset?.id, activeTab]);

  const loadDatasets = async () => {
    setLoading(true);
    try {
      const data = await api.listDatasets(studyId);
      setDatasets(data);
    } catch (err) {
      console.error('Failed to load datasets:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadCandidates = async () => {
    if (!studyId) return;
    setCandidatesLoading(true);
    try {
      const data = await api.listDatasetCandidates(studyId);
      setCandidates(data);
    } catch (err) {
      console.error('Failed to load candidates:', err);
    } finally {
      setCandidatesLoading(false);
    }
  };

  const handleImportCandidate = async (candidateId: string) => {
    if (!studyId) return;
    setImportingId(candidateId);
    try {
      const result = await api.importDatasetCandidate(studyId, candidateId);
      setCandidateActionMsg({ id: candidateId, type: 'success', text: `Imported "${result.dataset_name}" (${result.row_count?.toLocaleString() ?? '?'} rows)` });
      // Update candidate status locally
      setCandidates((prev) => prev.map((c) => c.id === candidateId ? { ...c, status: 'imported_by_user', imported_dataset_id: result.imported_dataset_id } : c));
      // Refresh datasets list to show new entry
      await loadDatasets();
      setTimeout(() => setCandidateActionMsg(null), 5000);
    } catch (err: any) {
      setCandidateActionMsg({ id: candidateId, type: 'error', text: err.message || 'Import failed' });
      setTimeout(() => setCandidateActionMsg(null), 5000);
    } finally {
      setImportingId(null);
    }
  };

  const handleRejectCandidate = async (candidateId: string) => {
    if (!studyId) return;
    setRejectingId(candidateId);
    try {
      await api.rejectDatasetCandidate(studyId, candidateId);
      setCandidates((prev) => prev.map((c) => c.id === candidateId ? { ...c, status: 'rejected_by_user' } : c));
    } catch (err) {
      console.error('Failed to reject candidate:', err);
    } finally {
      setRejectingId(null);
    }
  };

  const loadPreview = async (dsId: string, offset: number) => {
    setPreviewLoading(true);
    try {
      const res = await api.getDatasetPreview(dsId, offset, PREVIEW_PAGE_SIZE, studyId);
      setPreviewData(res);
      setPreviewOffset(offset);
    } catch (err) {
      console.error('Failed to load dataset preview:', err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleCreateUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!datasetName.trim() || !datasetUrl.trim()) {
      setFormError('Please provide both a dataset name and a valid URL.');
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.addDatasetUrl({
        name: datasetName.trim(),
        url: datasetUrl.trim(),
        description: datasetDesc.trim() || undefined,
        file_type: datasetType,
        study_id: studyId,
      });
      setDatasets([created, ...datasets]);
      setIsAddModalOpen(false);
      resetForm();
      setSelectedDataset(created);
    } catch (err: any) {
      setFormError(err.message || 'Failed to ingest dataset URL');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUploadFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!datasetName.trim() || !uploadFile) {
      setFormError('Please provide a dataset name and select a file.');
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('name', datasetName.trim());
      if (datasetDesc.trim()) formData.append('description', datasetDesc.trim());
      formData.append('file_type', datasetType);
      if (studyId) formData.append('study_id', studyId);

      const created = await api.uploadDataset(formData, studyId);
      setDatasets([created, ...datasets]);
      setIsAddModalOpen(false);
      resetForm();
      setSelectedDataset(created);
    } catch (err: any) {
      setFormError(err.message || 'Failed to process uploaded dataset');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRefresh = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const refreshed = await api.refreshDataset(id, studyId);
      setDatasets(datasets.map((d) => (d.id === id ? refreshed : d)));
      if (selectedDataset?.id === id) setSelectedDataset(refreshed);
      setRefreshNotification({
        id,
        message: 'Dataset verified with source. Metadata & statistics updated.',
        changed: true,
      });
      setTimeout(() => setRefreshNotification(null), 4000);
    } catch (err) {
      console.error('Failed to refresh dataset:', err);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to remove this dataset source?')) return;
    try {
      await api.deleteDataset(id, studyId);
      setDatasets(datasets.filter((d) => d.id !== id));
      if (selectedDataset?.id === id) setSelectedDataset(null);
    } catch (err) {
      console.error('Failed to delete dataset:', err);
    }
  };

  const handleOpenGenerate = (ds: DatasetSource, e: React.MouseEvent) => {
    e.stopPropagation();
    setGeneratingDataset(ds);
    setGenerationRun(null);
    setIsGenerateModalOpen(true);
  };

  const handleGeneratePersonas = async () => {
    if (!generatingDataset) return;
    setGenerating(true);
    try {
      const run = await api.generateDatasetPersonas(generatingDataset.id, {
        requested_count: personaCount,
        business_name: businessName,
        business_description: businessDesc,
        study_id: studyId,
      });
      setGenerationRun(run);
      // Update persona count in dataset card
      setDatasets(
        datasets.map((d) =>
          d.id === generatingDataset.id
            ? { ...d, persona_count_generated: (d.persona_count_generated || 0) + run.generated_count }
            : d
        )
      );
    } catch (err: any) {
      alert(err.message || 'Persona generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const resetForm = () => {
    setDatasetName('');
    setDatasetUrl('');
    setDatasetDesc('');
    setUploadFile(null);
    setFormError(null);
  };

  return (
    <div style={{ flex: 1, padding: '36px 40px', maxWidth: '1440px', margin: '0 auto', width: '100%' }}>
      {/* Header Bar */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '28px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <h1 style={{ fontSize: '1.65rem', fontWeight: 700, color: '#f4f7f7', letterSpacing: '-0.02em', margin: 0 }}>
              Dataset Sources
            </h1>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 600,
                color: '#14B8A6',
                background: 'rgba(20, 184, 166, 0.12)',
                border: '1px solid rgba(20, 184, 166, 0.25)',
                borderRadius: '6px',
                padding: '2px 8px',
                textTransform: 'uppercase',
              }}
            >
              Data Lab
            </span>
          </div>
          <p style={{ fontSize: '0.88rem', color: '#8D9999', margin: 0, maxWidth: '680px', lineHeight: 1.5 }}>
            Attach empirical datasets (CSV, JSON, XLSX) to ground market segmentation and persona synthesis in real-world statistical distributions.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={() => setIsOpenRouterModalOpen(true)}
            style={{
              background: 'rgba(255, 255, 255, 0.04)',
              border: '1px solid #202727',
              color: '#cbd5e1',
              borderRadius: '8px',
              padding: '9px 15px',
              fontSize: '0.84rem',
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.18s ease',
            }}
          >
            <Cpu size={15} color="#22D3EE" /> LLM Gateway
          </button>

          <button
            onClick={() => {
              resetForm();
              setIsAddModalOpen(true);
            }}
            style={{
              background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
              border: 'none',
              color: '#080A0A',
              borderRadius: '8px',
              padding: '9px 18px',
              fontSize: '0.86rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 4px 14px rgba(20, 184, 166, 0.25)',
              transition: 'all 0.18s ease',
            }}
          >
            <Plus size={16} strokeWidth={2.4} /> Add Dataset
          </button>
        </div>
      </div>

      {/* Main Panel Tab Switcher */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', background: 'rgba(255,255,255,0.03)', border: '1px solid #202727', borderRadius: '10px', padding: '4px', width: 'fit-content' }}>
        {([
          { key: 'sources', label: 'Dataset Sources', icon: <Database size={14} /> },
          { key: 'discovered', label: `Discovered${candidates.length > 0 ? ` (${candidates.filter(c => c.status === 'discovered').length})` : ''}`, icon: <Bot size={14} /> },
        ] as { key: 'sources' | 'discovered'; label: string; icon: React.ReactNode }[]).map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setMainTab(key)}
            style={{
              background: mainTab === key ? 'rgba(20, 184, 166, 0.15)' : 'transparent',
              border: mainTab === key ? '1px solid rgba(20, 184, 166, 0.35)' : '1px solid transparent',
              color: mainTab === key ? '#22D3EE' : '#8D9999',
              borderRadius: '7px',
              padding: '7px 16px',
              fontSize: '0.82rem',
              fontWeight: mainTab === key ? 600 : 400,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.15s ease',
            }}
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Global Refresh Notification Banner */}
      {refreshNotification && (
        <div
          style={{
            background: 'rgba(20, 184, 166, 0.12)',
            border: '1px solid rgba(20, 184, 166, 0.3)',
            borderRadius: '8px',
            padding: '10px 16px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '0.84rem',
            color: '#22D3EE',
          }}
        >
          <CheckCircle2 size={16} color="#14B8A6" />
          <span>{refreshNotification.message}</span>
        </div>
      )}

      {/* Summary Metrics Banner */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '14px',
          marginBottom: '28px',
        }}
      >
        <div style={{ background: '#0D1111', border: '1px solid #202727', borderRadius: '10px', padding: '16px' }}>
          <div style={{ fontSize: '0.76rem', color: '#8D9999', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
            Connected Datasets
          </div>
          <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#f4f7f7' }}>{datasets.length}</div>
        </div>

        <div style={{ background: '#0D1111', border: '1px solid #202727', borderRadius: '10px', padding: '16px' }}>
          <div style={{ fontSize: '0.76rem', color: '#8D9999', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
            Total Empirical Records
          </div>
          <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#14B8A6' }}>
            {datasets.reduce((acc, d) => acc + (d.row_count || 0), 0).toLocaleString()}
          </div>
        </div>

        <div style={{ background: '#0D1111', border: '1px solid #202727', borderRadius: '10px', padding: '16px' }}>
          <div style={{ fontSize: '0.76rem', color: '#8D9999', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
            Discovered Segments
          </div>
          <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#22D3EE' }}>
            {datasets.reduce((acc, d) => acc + (d.segments?.length || 0), 0)}
          </div>
        </div>

        <div style={{ background: '#0D1111', border: '1px solid #202727', borderRadius: '10px', padding: '16px' }}>
          <div style={{ fontSize: '0.76rem', color: '#8D9999', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>
            Grounded Personas Synthesized
          </div>
          <div style={{ fontSize: '1.45rem', fontWeight: 700, color: '#10B981' }}>
            {datasets.reduce((acc, d) => acc + (d.persona_count_generated || 0), 0)}
          </div>
        </div>
      </div>

      {mainTab === 'sources' && (<>
      {loading ? (
        <div style={{ padding: '60px', textAlign: 'center', color: '#8D9999' }}>
          <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px auto' }} color="#14B8A6" />
          <p style={{ fontSize: '0.9rem' }}>Loading empirical datasets from database...</p>
        </div>
      ) : datasets.length === 0 ? (
        <div
          style={{
            background: '#0D1111',
            border: '1px dashed #202727',
            borderRadius: '12px',
            padding: '50px 24px',
            textAlign: 'center',
          }}
        >
          <Database size={36} color="#8D9999" style={{ margin: '0 auto 14px auto', opacity: 0.6 }} />
          <h3 style={{ fontSize: '1.05rem', color: '#f4f7f7', margin: '0 0 6px 0' }}>No Datasets Connected</h3>
          <p style={{ fontSize: '0.86rem', color: '#8D9999', maxWidth: '440px', margin: '0 auto 20px auto' }}>
            Add public survey URLs or upload structured CSV/JSON files to ground your research in real empirical distributions.
          </p>
          <button
            onClick={() => setIsAddModalOpen(true)}
            style={{
              background: 'rgba(20, 184, 166, 0.12)',
              border: '1px solid rgba(20, 184, 166, 0.3)',
              color: '#22D3EE',
              borderRadius: '8px',
              padding: '8px 18px',
              fontSize: '0.84rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            + Add First Dataset
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
          {datasets.map((ds) => (
            <div
              key={ds.id}
              data-testid={`dataset-card-${ds.id}`}
              onClick={() => {
                setSelectedDataset(ds);
                setActiveTab('overview');
              }}
              style={{
                background: '#0D1111',
                border: '1px solid #202727',
                borderRadius: '12px',
                padding: '20px',
                cursor: 'pointer',
                transition: 'all 0.18s ease',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(20, 184, 166, 0.4)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#202727')}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {ds.source_type === 'url' ? <Link size={16} color="#22D3EE" /> : <Upload size={16} color="#14B8A6" />}
                    <h3 style={{ fontSize: '0.98rem', fontWeight: 600, color: '#f4f7f7', margin: 0 }}>{ds.name}</h3>
                  </div>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '2px 7px',
                      borderRadius: '4px',
                      background: ds.status === 'ready' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                      color: ds.status === 'ready' ? '#10B981' : '#F59E0B',
                      textTransform: 'uppercase',
                    }}
                  >
                    {ds.status}
                  </span>
                </div>

                <p style={{ fontSize: '0.82rem', color: '#8D9999', margin: '0 0 14px 0', lineHeight: 1.4, minHeight: '34px' }}>
                  {ds.description || (ds.source_url ? `Ingested from ${ds.source_url}` : `Uploaded file ${ds.original_file_name}`)}
                </p>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(3, 1fr)',
                    gap: '8px',
                    background: 'rgba(0, 0, 0, 0.25)',
                    padding: '10px',
                    borderRadius: '8px',
                    marginBottom: '16px',
                    fontSize: '0.78rem',
                  }}
                >
                  <div>
                    <span style={{ color: '#535D5D', display: 'block', fontSize: '0.7rem' }}>ROWS</span>
                    <strong style={{ color: '#cbd5e1' }}>{ds.row_count?.toLocaleString() || 0}</strong>
                  </div>
                  <div>
                    <span style={{ color: '#535D5D', display: 'block', fontSize: '0.7rem' }}>COLUMNS</span>
                    <strong style={{ color: '#cbd5e1' }}>{ds.column_count || 0}</strong>
                  </div>
                  <div>
                    <span style={{ color: '#535D5D', display: 'block', fontSize: '0.7rem' }}>SEGMENTS</span>
                    <strong style={{ color: '#22D3EE' }}>{ds.segments?.length || 0}</strong>
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderTop: '1px solid #202727',
                  paddingTop: '12px',
                  marginTop: '6px',
                }}
              >
                <div style={{ display: 'flex', gap: '8px' }}>
                  {ds.source_type === 'url' && (
                    <button
                      onClick={(e) => handleRefresh(ds.id, e)}
                      title="Refresh URL data"
                      style={{
                        background: 'transparent',
                        border: '1px solid #202727',
                        color: '#8D9999',
                        borderRadius: '6px',
                        padding: '5px 8px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '0.75rem',
                      }}
                    >
                      <RefreshCw size={12} /> Refresh
                    </button>
                  )}
                  <button
                    onClick={(e) => handleDelete(ds.id, e)}
                    title="Delete dataset"
                    style={{
                      background: 'transparent',
                      border: '1px solid #202727',
                      color: '#ef4444',
                      borderRadius: '6px',
                      padding: '5px 8px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '0.75rem',
                    }}
                  >
                    <Trash2 size={12} /> Delete
                  </button>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedDataset(ds);
                      setActiveTab('preview');
                    }}
                    style={{
                      background: 'rgba(34, 211, 238, 0.08)',
                      border: '1px solid rgba(34, 211, 238, 0.25)',
                      color: '#22D3EE',
                      borderRadius: '6px',
                      padding: '5px 10px',
                      fontSize: '0.76rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Table size={12} /> Preview
                  </button>

                  <button
                    onClick={(e) => handleOpenGenerate(ds, e)}
                    style={{
                      background: 'rgba(20, 184, 166, 0.12)',
                      border: '1px solid rgba(20, 184, 166, 0.3)',
                      color: '#14B8A6',
                      borderRadius: '6px',
                      padding: '5px 10px',
                      fontSize: '0.76rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Sparkles size={12} /> Synthesize
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dataset Detail Modal */}
      {selectedDataset && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
        >
          {/* Backdrop */}
          <div
            data-testid="dataset-detail-modal-backdrop"
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0, 0, 0, 0.82)',
              backdropFilter: 'blur(6px)',
            }}
            onClick={() => setSelectedDataset(null)}
          />

          {/* Modal Container */}
          <div
            style={{
              position: 'relative',
              zIndex: 1,
              background: '#0D1111',
              border: '1px solid #202727',
              borderRadius: '14px',
              width: '100%',
              maxWidth: '960px',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '20px 24px',
                borderBottom: '1px solid #202727',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2 style={{ fontSize: '1.18rem', fontWeight: 600, color: '#f4f7f7', margin: 0 }}>
                    {selectedDataset.name}
                  </h2>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      padding: '2px 7px',
                      borderRadius: '4px',
                      background: 'rgba(20, 184, 166, 0.12)',
                      color: '#22D3EE',
                    }}
                  >
                    {selectedDataset.file_type.toUpperCase()}
                  </span>
                </div>
                <div style={{ fontSize: '0.78rem', color: '#8D9999', marginTop: '3px' }}>
                  {selectedDataset.row_count?.toLocaleString()} rows · {selectedDataset.column_count} columns · Status: {selectedDataset.status}
                </div>
              </div>

              <button
                onClick={() => setSelectedDataset(null)}
                style={{ background: 'transparent', border: 'none', color: '#8D9999', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Tabs Bar */}
            <div style={{ display: 'flex', borderBottom: '1px solid #202727', padding: '0 24px', gap: '20px' }}>
              {(['overview', 'preview', 'schema', 'stats', 'quality', 'segments'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  data-testid={`tab-${tab}`}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    borderBottom: activeTab === tab ? '2px solid #14B8A6' : '2px solid transparent',
                    color: activeTab === tab ? '#22D3EE' : '#8D9999',
                    fontWeight: activeTab === tab ? 600 : 400,
                    fontSize: '0.84rem',
                    padding: '12px 4px',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {tab === 'stats'
                    ? 'Descriptive Statistics'
                    : tab === 'quality'
                    ? `Data Quality (${selectedDataset.schema_metadata?.warnings?.length || 0})`
                    : tab === 'preview'
                    ? 'Data Preview'
                    : tab === 'segments'
                    ? `Discovered Segments (${selectedDataset.segments?.length || 0})`
                    : tab}
                </button>
              ))}
            </div>

            {/* Content Area */}
            <div data-testid="modal-content-area" style={{ padding: '24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '10px', padding: '16px' }}>
                    <div style={{ fontSize: '0.82rem', color: '#8D9999', marginBottom: '8px' }}>Description</div>
                    <div style={{ fontSize: '0.88rem', color: '#f4f7f7', lineHeight: 1.5 }}>
                      {selectedDataset.description || 'No description provided.'}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                    <div style={{ background: '#111616', border: '1px solid #202727', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ fontSize: '0.72rem', color: '#8D9999' }}>SOURCE TYPE</div>
                      <div style={{ fontSize: '0.86rem', fontWeight: 600, color: '#f4f7f7' }}>{selectedDataset.source_type.toUpperCase()}</div>
                    </div>
                    <div style={{ background: '#111616', border: '1px solid #202727', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ fontSize: '0.72rem', color: '#8D9999' }}>CONTENT HASH</div>
                      <div style={{ fontSize: '0.78rem', fontFamily: 'monospace', color: '#22D3EE' }}>
                        {selectedDataset.content_hash ? selectedDataset.content_hash.slice(0, 16) + '...' : 'Calculated on ingest'}
                      </div>
                    </div>
                    <div style={{ background: '#111616', border: '1px solid #202727', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ fontSize: '0.72rem', color: '#8D9999' }}>LAST PROCESSED</div>
                      <div style={{ fontSize: '0.86rem', fontWeight: 600, color: '#f4f7f7' }}>
                        {selectedDataset.last_processed_at ? new Date(selectedDataset.last_processed_at).toLocaleString() : 'Just now'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Data Preview Tab */}
              {activeTab === 'preview' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: '0.84rem', color: '#8D9999' }}>
                      Showing records {previewOffset + 1}–{Math.min(previewOffset + PREVIEW_PAGE_SIZE, previewData?.total_rows || selectedDataset.row_count)} of {previewData?.total_rows || selectedDataset.row_count}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        disabled={previewOffset === 0 || previewLoading}
                        onClick={() => loadPreview(selectedDataset.id, Math.max(0, previewOffset - PREVIEW_PAGE_SIZE))}
                        style={{
                          background: '#111616',
                          border: '1px solid #202727',
                          color: previewOffset === 0 ? '#535D5D' : '#f4f7f7',
                          borderRadius: '6px',
                          padding: '4px 8px',
                          cursor: previewOffset === 0 ? 'default' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '0.78rem',
                        }}
                      >
                        <ChevronLeft size={14} /> Previous
                      </button>
                      <button
                        disabled={!previewData || previewOffset + PREVIEW_PAGE_SIZE >= previewData.total_rows || previewLoading}
                        onClick={() => loadPreview(selectedDataset.id, previewOffset + PREVIEW_PAGE_SIZE)}
                        style={{
                          background: '#111616',
                          border: '1px solid #202727',
                          color: !previewData || previewOffset + PREVIEW_PAGE_SIZE >= previewData.total_rows ? '#535D5D' : '#f4f7f7',
                          borderRadius: '6px',
                          padding: '4px 8px',
                          cursor: !previewData || previewOffset + PREVIEW_PAGE_SIZE >= previewData.total_rows ? 'default' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '0.78rem',
                        }}
                      >
                        Next <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>

                  {previewLoading ? (
                    <div style={{ padding: '40px', textAlign: 'center', color: '#8D9999' }}>
                      <RefreshCw size={20} className="spin" style={{ margin: '0 auto 8px auto' }} color="#14B8A6" />
                      <span>Loading records...</span>
                    </div>
                  ) : previewData && previewData.rows.length > 0 ? (
                    <div style={{ overflowX: 'auto', border: '1px solid #202727', borderRadius: '8px' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
                        <thead>
                          <tr style={{ background: '#111616', borderBottom: '1px solid #202727', color: '#8D9999' }}>
                            <th style={{ padding: '8px 12px', width: '40px' }}>#</th>
                            {previewData.columns.map((col) => (
                              <th key={col} style={{ padding: '8px 12px', fontWeight: 600 }}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {previewData.rows.map((row, idx) => (
                            <tr key={idx} style={{ borderBottom: '1px solid #161c1c' }}>
                              <td style={{ padding: '8px 12px', color: '#535D5D', fontSize: '0.74rem' }}>{previewOffset + idx + 1}</td>
                              {previewData.columns.map((col) => (
                                <td key={col} style={{ padding: '8px 12px', color: '#f4f7f7' }}>
                                  {row[col] !== null && row[col] !== undefined ? String(row[col]) : <em style={{ color: '#535D5D' }}>null</em>}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div style={{ padding: '30px', textAlign: 'center', color: '#8D9999' }}>
                      No preview records available.
                    </div>
                  )}
                </div>
              )}

              {/* Schema Tab */}
              {activeTab === 'schema' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ fontSize: '0.84rem', color: '#8D9999' }}>Inferred Column Types & Missingness Profiling</div>
                  <div style={{ overflowX: 'auto', border: '1px solid #202727', borderRadius: '8px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: '#111616', borderBottom: '1px solid #202727', color: '#8D9999' }}>
                          <th style={{ padding: '8px 12px' }}>Column</th>
                          <th style={{ padding: '8px 12px' }}>Type</th>
                          <th style={{ padding: '8px 12px' }}>Missing Rate</th>
                          <th style={{ padding: '8px 12px' }}>Distinct Values</th>
                          <th style={{ padding: '8px 12px' }}>Sample Values</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedDataset.schema_metadata?.columns?.map((col) => (
                          <tr key={col.name} style={{ borderBottom: '1px solid #161c1c' }}>
                            <td style={{ padding: '10px 12px', fontWeight: 600, color: '#f4f7f7' }}>{col.name}</td>
                            <td style={{ padding: '10px 12px' }}>
                              <span
                                style={{
                                  padding: '2px 6px',
                                  borderRadius: '4px',
                                  fontSize: '0.72rem',
                                  background: col.type === 'numeric' ? 'rgba(34, 211, 238, 0.12)' : col.type === 'categorical' ? 'rgba(20, 184, 166, 0.12)' : 'rgba(255, 255, 255, 0.06)',
                                  color: col.type === 'numeric' ? '#22D3EE' : col.type === 'categorical' ? '#14B8A6' : '#8D9999',
                                }}
                              >
                                {col.type}
                              </span>
                            </td>
                            <td style={{ padding: '10px 12px', color: col.missing_percentage > 10 ? '#ef4444' : '#8D9999' }}>
                              {col.missing_percentage}%
                            </td>
                            <td style={{ padding: '10px 12px', color: '#f4f7f7' }}>{col.unique_count}</td>
                            <td style={{ padding: '10px 12px', color: '#8D9999' }}>
                              {col.sample_values?.slice(0, 3).join(', ') || 'N/A'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Statistics Tab */}
              {activeTab === 'stats' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Numeric Stats */}
                  {selectedDataset.statistics?.numeric && Object.keys(selectedDataset.statistics.numeric).length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '0.88rem', color: '#22D3EE', margin: '0 0 10px 0', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                        Numeric Distributions
                      </h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                        {Object.entries(selectedDataset.statistics.numeric).map(([colName, stat]) => (
                          <div key={colName} style={{ background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '12px' }}>
                            <div style={{ fontWeight: 600, fontSize: '0.86rem', color: '#f4f7f7', marginBottom: '6px' }}>{colName}</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', fontSize: '0.78rem' }}>
                              <div><span style={{ color: '#8D9999' }}>Min:</span> {stat.min}</div>
                              <div><span style={{ color: '#8D9999' }}>Median:</span> <strong style={{ color: '#14B8A6' }}>{stat.median}</strong></div>
                              <div><span style={{ color: '#8D9999' }}>Max:</span> {stat.max}</div>
                              <div><span style={{ color: '#8D9999' }}>Mean:</span> {stat.mean}</div>
                              <div><span style={{ color: '#8D9999' }}>Std:</span> {stat.std}</div>
                              <div><span style={{ color: '#8D9999' }}>IQR:</span> {stat.iqr}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Categorical Stats */}
                  {selectedDataset.statistics?.categorical && Object.keys(selectedDataset.statistics.categorical).length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '0.88rem', color: '#14B8A6', margin: '0 0 10px 0', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                        Categorical Frequencies
                      </h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                        {Object.entries(selectedDataset.statistics.categorical).map(([colName, cat]) => (
                          <div key={colName} style={{ background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '12px' }}>
                            <div style={{ fontWeight: 600, fontSize: '0.86rem', color: '#f4f7f7', marginBottom: '8px' }}>{colName}</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                              {cat.top_categories?.slice(0, 5).map((tc) => (
                                <div key={tc.category}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', marginBottom: '2px' }}>
                                    <span style={{ color: '#cbd5e1' }}>{tc.category}</span>
                                    <span style={{ color: '#14B8A6', fontWeight: 600 }}>{tc.percentage}% ({tc.count})</span>
                                  </div>
                                  <div style={{ width: '100%', height: '4px', background: '#202727', borderRadius: '2px', overflow: 'hidden' }}>
                                    <div style={{ width: `${tc.percentage}%`, height: '100%', background: '#14B8A6', borderRadius: '2px' }} />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Data Quality Tab */}
              {activeTab === 'quality' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontSize: '0.84rem', color: '#8D9999' }}>Data Integrity Auditing & Anomaly Detection</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '14px' }}>
                      <div style={{ fontSize: '0.74rem', color: '#8D9999' }}>OVERALL MISSING CELL RATE</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: (selectedDataset.schema_metadata?.missing_values_percentage || 0) > 5 ? '#F59E0B' : '#10B981' }}>
                        {selectedDataset.schema_metadata?.missing_values_percentage || 0}%
                      </div>
                    </div>
                    <div style={{ background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '14px' }}>
                      <div style={{ fontSize: '0.74rem', color: '#8D9999' }}>DUPLICATE ROWS DETECTED</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: (selectedDataset.schema_metadata?.duplicate_rows || 0) > 0 ? '#F59E0B' : '#10B981' }}>
                        {selectedDataset.schema_metadata?.duplicate_rows || 0}
                      </div>
                    </div>
                  </div>

                  {selectedDataset.schema_metadata?.warnings && selectedDataset.schema_metadata.warnings.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                      {selectedDataset.schema_metadata.warnings.map((w: string, i: number) => (
                        <div
                          key={i}
                          style={{
                            background: 'rgba(245, 158, 11, 0.08)',
                            border: '1px solid rgba(245, 158, 11, 0.25)',
                            borderRadius: '8px',
                            padding: '10px 14px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            fontSize: '0.82rem',
                            color: '#F59E0B',
                          }}
                        >
                          <AlertTriangle size={16} />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div
                      style={{
                        background: 'rgba(16, 185, 129, 0.08)',
                        border: '1px solid rgba(16, 185, 129, 0.25)',
                        borderRadius: '8px',
                        padding: '12px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        fontSize: '0.84rem',
                        color: '#10B981',
                      }}
                    >
                      <CheckCircle2 size={16} />
                      <span>Dataset quality audit passed with zero integrity anomalies.</span>
                    </div>
                  )}
                </div>
              )}

              {/* Segments Tab */}
              {activeTab === 'segments' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontSize: '0.84rem', color: '#8D9999' }}>
                    Mathematically derived segments based on feature distributions. Personas will be synthesized according to these exact population share quotas.
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '14px' }}>
                    {selectedDataset.segments?.map((seg) => (
                      <div key={seg.id} style={{ background: '#111616', border: '1px solid #202727', borderRadius: '10px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.92rem', color: '#22D3EE' }}>{seg.name}</span>
                          <span style={{ fontSize: '0.78rem', background: 'rgba(20, 184, 166, 0.12)', color: '#14B8A6', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                            {seg.population_percentage}% Share
                          </span>
                        </div>

                        {seg.constraints?.rule_description && (
                          <div style={{ fontSize: '0.8rem', color: '#f4f7f7', lineHeight: 1.4 }}>
                            {seg.constraints.rule_description}
                          </div>
                        )}

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.78rem', background: 'rgba(0,0,0,0.3)', padding: '8px', borderRadius: '6px' }}>
                          <div>
                            <span style={{ color: '#8D9999' }}>Age Range:</span> {seg.constraints?.age_range ? `${seg.constraints.age_range[0]}–${seg.constraints.age_range[1]}` : 'N/A'}
                          </div>
                          <div>
                            <span style={{ color: '#8D9999' }}>Monthly Budget:</span> ~৳{seg.constraints?.monthly_budget?.median || 'N/A'}
                          </div>
                          <div>
                            <span style={{ color: '#8D9999' }}>Tech Familiarity:</span> {seg.constraints?.technology_familiarity || 'Medium'}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid #202727', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#0D1111' }}>
              <button
                onClick={() => setSelectedDataset(null)}
                style={{ background: 'transparent', border: '1px solid #202727', borderRadius: '8px', padding: '8px 16px', color: '#8D9999', cursor: 'pointer', fontSize: '0.84rem' }}
              >
                Close
              </button>

              <button
                onClick={(e) => handleOpenGenerate(selectedDataset, e)}
                style={{
                  background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '9px 18px',
                  color: '#080A0A',
                  fontWeight: 600,
                  fontSize: '0.84rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Sparkles size={15} /> Synthesize Grounded Personas
              </button>
            </div>
          </div>
        </div>
      )}

      </>
      )}

      {/* Discovered Dataset Candidates Panel */}
      {mainTab === 'discovered' && (
        <div style={{ marginTop: '4px' }}>
          {/* Action banner */}
          {candidateActionMsg && (
            <div style={{
              background: candidateActionMsg.type === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
              border: `1px solid ${candidateActionMsg.type === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
              borderRadius: '8px', padding: '10px 16px', marginBottom: '20px',
              display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.84rem',
              color: candidateActionMsg.type === 'success' ? '#10B981' : '#EF4444',
            }}>
              {candidateActionMsg.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
              <span>{candidateActionMsg.text}</span>
            </div>
          )}

          {candidatesLoading ? (
            <div style={{ padding: '60px', textAlign: 'center', color: '#8D9999' }}>
              <RefreshCw size={24} className="spin" style={{ margin: '0 auto 12px auto' }} color="#14B8A6" />
              <p style={{ fontSize: '0.9rem' }}>Searching public data repositories...</p>
            </div>
          ) : candidates.length === 0 ? (
            <div style={{
              background: '#0D1111', border: '1px dashed #202727', borderRadius: '12px',
              padding: '60px 24px', textAlign: 'center',
            }}>
              <Bot size={38} color="#8D9999" style={{ margin: '0 auto 16px auto', opacity: 0.5 }} />
              <h3 style={{ fontSize: '1.05rem', color: '#f4f7f7', margin: '0 0 8px 0' }}>No Discovered Datasets Yet</h3>
              <p style={{ fontSize: '0.86rem', color: '#8D9999', maxWidth: '460px', margin: '0 auto 6px auto' }}>
                Run autonomous research from the Evidence Laboratory. BebshaX will automatically discover, evaluate,
                and present public datasets relevant to your study.
              </p>
            </div>
          ) : (
            <div>
              <div style={{ marginBottom: '18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <p style={{ fontSize: '0.84rem', color: '#8D9999', margin: 0 }}>
                    {candidates.filter(c => c.status === 'discovered').length} pending &nbsp;·&nbsp;
                    {candidates.filter(c => c.status === 'auto_imported' || c.status === 'imported_by_user').length} imported &nbsp;·&nbsp;
                    {candidates.filter(c => c.status === 'rejected_by_user').length} rejected
                  </p>
                </div>
                <button
                  onClick={loadCandidates}
                  style={{ background: 'transparent', border: '1px solid #202727', color: '#8D9999', borderRadius: '7px', padding: '6px 12px', fontSize: '0.8rem', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '5px' }}
                >
                  <RefreshCw size={13} /> Refresh
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {candidates.map(c => {
                  const isImported = c.status === 'auto_imported' || c.status === 'imported_by_user';
                  const isRejected = c.status === 'rejected_by_user';
                  const isPending = c.status === 'discovered';
                  return (
                    <div
                      key={c.id}
                      style={{
                        background: isRejected ? 'rgba(255,255,255,0.01)' : '#0D1111',
                        border: `1px solid ${isImported ? 'rgba(16,185,129,0.3)' : isRejected ? '#202727' : 'rgba(20,184,166,0.2)'}`,
                        borderRadius: '10px', padding: '18px 20px',
                        opacity: isRejected ? 0.55 : 1,
                        transition: 'border-color 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '0.95rem', fontWeight: 600, color: isRejected ? '#8D9999' : '#f4f7f7' }}>{c.name}</span>
                            {isImported && <span style={{ fontSize: '0.7rem', fontWeight: 600, background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.3)', color: '#10B981', borderRadius: '4px', padding: '1px 7px' }}>IMPORTED</span>}
                            {c.status === 'auto_imported' && <span style={{ fontSize: '0.68rem', color: '#8D9999' }}>Auto</span>}
                            {isRejected && <span style={{ fontSize: '0.7rem', fontWeight: 600, background: 'rgba(100,100,100,0.12)', border: '1px solid #202727', color: '#8D9999', borderRadius: '4px', padding: '1px 7px' }}>REJECTED</span>}
                            {c.diversity_tag && <span style={{ fontSize: '0.68rem', color: '#22D3EE', background: 'rgba(34,211,238,0.07)', border: '1px solid rgba(34,211,238,0.15)', borderRadius: '4px', padding: '1px 7px' }}>{c.diversity_tag.toUpperCase()}</span>}
                            {c.file_type && <span style={{ fontSize: '0.68rem', color: '#8D9999' }}>{c.file_type.toUpperCase()}</span>}
                          </div>
                          {c.description && <p style={{ fontSize: '0.83rem', color: '#8D9999', margin: '0 0 10px 0', lineHeight: 1.5 }}>{c.description}</p>}
                          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '10px' }}>
                            <div style={{ minWidth: '140px' }}>
                              <div style={{ fontSize: '0.72rem', color: '#8D9999', marginBottom: '3px', display: 'flex', justifyContent: 'space-between' }}>
                                <span>Quality</span><span style={{ color: '#22D3EE' }}>{Math.round(c.quality_score * 100)}%</span>
                              </div>
                              <div style={{ background: '#202727', borderRadius: '3px', height: '4px' }}>
                                <div style={{ background: 'linear-gradient(90deg,#14B8A6,#22D3EE)', borderRadius: '3px', height: '4px', width: `${Math.round(c.quality_score * 100)}%` }} />
                              </div>
                            </div>
                            <div style={{ minWidth: '140px' }}>
                              <div style={{ fontSize: '0.72rem', color: '#8D9999', marginBottom: '3px', display: 'flex', justifyContent: 'space-between' }}>
                                <span>Relevance</span><span style={{ color: '#22D3EE' }}>{Math.round(c.relevance_score * 100)}%</span>
                              </div>
                              <div style={{ background: '#202727', borderRadius: '3px', height: '4px' }}>
                                <div style={{ background: 'linear-gradient(90deg,#0D9488,#14B8A6)', borderRadius: '3px', height: '4px', width: `${Math.round(c.relevance_score * 100)}%` }} />
                              </div>
                            </div>
                            {c.estimated_rows != null && (
                              <div style={{ fontSize: '0.78rem', color: '#8D9999', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Table size={12} /> ~{c.estimated_rows.toLocaleString()} rows
                              </div>
                            )}
                            {c.source_name && (
                              <div style={{ fontSize: '0.78rem', color: '#8D9999', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Globe size={12} /> {c.source_name}
                              </div>
                            )}
                          </div>
                          {c.source_url && (
                            <a href={c.source_url} target="_blank" rel="noopener noreferrer"
                              style={{ fontSize: '0.78rem', color: '#22D3EE', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '3px' }}
                            >
                              <ArrowRight size={11} /> View Source
                            </a>
                          )}
                        </div>

                        {isPending && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '7px', flexShrink: 0 }}>
                            <button
                              id={`import-candidate-${c.id}`}
                              onClick={() => handleImportCandidate(c.id)}
                              disabled={importingId === c.id}
                              style={{
                                background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                                border: 'none', color: '#080A0A', borderRadius: '7px',
                                padding: '7px 14px', fontSize: '0.81rem', fontWeight: 600,
                                cursor: importingId === c.id ? 'wait' : 'pointer',
                                display: 'flex', alignItems: 'center', gap: '5px',
                                opacity: importingId === c.id ? 0.7 : 1,
                                whiteSpace: 'nowrap',
                              }}
                            >
                              <Download size={13} />
                              {importingId === c.id ? 'Importing...' : 'Import'}
                            </button>
                            <button
                              id={`reject-candidate-${c.id}`}
                              onClick={() => handleRejectCandidate(c.id)}
                              disabled={rejectingId === c.id}
                              style={{
                                background: 'transparent', border: '1px solid #202727', color: '#8D9999',
                                borderRadius: '7px', padding: '7px 14px', fontSize: '0.81rem',
                                cursor: rejectingId === c.id ? 'wait' : 'pointer',
                                display: 'flex', alignItems: 'center', gap: '5px',
                                opacity: rejectingId === c.id ? 0.5 : 1,
                                whiteSpace: 'nowrap',
                              }}
                            >
                              <ThumbsDown size={13} />
                              {rejectingId === c.id ? '...' : 'Reject'}
                            </button>
                          </div>
                        )}

                        {isImported && (
                          <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: '6px', color: '#10B981', fontSize: '0.82rem' }}>
                            <CheckCircle2 size={16} /> Added to Sources
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Add Dataset Modal */}
      {isAddModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
        >
          {/* Backdrop */}
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0, 0, 0, 0.8)',
              backdropFilter: 'blur(6px)',
            }}
            onClick={() => setIsAddModalOpen(false)}
          />

          {/* Modal Container */}
          <div
            style={{
              position: 'relative',
              zIndex: 1,
              background: '#0D1111',
              border: '1px solid #202727',
              borderRadius: '14px',
              width: '100%',
              maxWidth: '560px',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '20px 24px', borderBottom: '1px solid #202727', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#f4f7f7', margin: 0 }}>Add Dataset Source</h2>
              <button onClick={() => setIsAddModalOpen(false)} style={{ background: 'transparent', border: 'none', color: '#8D9999', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', borderBottom: '1px solid #202727', padding: '0 24px', gap: '20px' }}>
              <button
                onClick={() => setAddMode('url')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  borderBottom: addMode === 'url' ? '2px solid #14B8A6' : '2px solid transparent',
                  color: addMode === 'url' ? '#22D3EE' : '#8D9999',
                  fontWeight: addMode === 'url' ? 600 : 400,
                  fontSize: '0.86rem',
                  padding: '12px 4px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Link size={14} /> URL Ingestion
              </button>
              <button
                onClick={() => setAddMode('upload')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  borderBottom: addMode === 'upload' ? '2px solid #14B8A6' : '2px solid transparent',
                  color: addMode === 'upload' ? '#22D3EE' : '#8D9999',
                  fontWeight: addMode === 'upload' ? 600 : 400,
                  fontSize: '0.86rem',
                  padding: '12px 4px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Upload size={14} /> File Upload
              </button>
            </div>

            <form onSubmit={addMode === 'url' ? handleCreateUrl : handleUploadFile} style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {formError && (
                <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px', padding: '10px', color: '#f87171', fontSize: '0.82rem' }}>
                  {formError}
                </div>
              )}

              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Dataset Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Bangladesh Student Tech Spending Survey 2026"
                  value={datasetName}
                  onChange={(e) => setDatasetName(e.target.value)}
                  style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '9px 12px', color: '#f4f7f7', fontSize: '0.86rem' }}
                />
              </div>

              {addMode === 'url' ? (
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Dataset URL *</label>
                  <input
                    type="url"
                    required
                    placeholder="https://example.com/survey-data.csv"
                    value={datasetUrl}
                    onChange={(e) => setDatasetUrl(e.target.value)}
                    style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '9px 12px', color: '#f4f7f7', fontSize: '0.86rem' }}
                  />
                  <span style={{ fontSize: '0.72rem', color: '#535D5D', marginTop: '4px', display: 'block' }}>
                    SSRF protection active. Direct raw CSV, JSON, or TSV links supported.
                  </span>
                </div>
              ) : (
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Select File (CSV, JSON, XLSX, TSV) *</label>
                  <input
                    type="file"
                    required
                    accept=".csv,.json,.jsonl,.tsv,.xlsx"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    style={{ width: '100%', background: '#111616', border: '1px dashed #202727', borderRadius: '8px', padding: '12px', color: '#8D9999', fontSize: '0.84rem' }}
                  />
                </div>
              )}

              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Description</label>
                <textarea
                  rows={2}
                  placeholder="Optional context about survey demographics, sample size, or collection methodology..."
                  value={datasetDesc}
                  onChange={(e) => setDatasetDesc(e.target.value)}
                  style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '9px 12px', color: '#f4f7f7', fontSize: '0.86rem', resize: 'vertical' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  style={{ background: 'transparent', border: '1px solid #202727', borderRadius: '8px', padding: '8px 16px', color: '#8D9999', cursor: 'pointer', fontSize: '0.84rem' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '9px 18px',
                    color: '#080A0A',
                    fontWeight: 600,
                    fontSize: '0.84rem',
                    cursor: submitting ? 'not-allowed' : 'pointer',
                  }}
                >
                  {submitting ? 'Processing & Profiling...' : 'Ingest & Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Persona Generation / Synthesis Modal */}
      {isGenerateModalOpen && generatingDataset && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
          <div style={{ background: '#0D1111', border: '1px solid #202727', borderRadius: '16px', maxWidth: '520px', width: '100%', padding: '24px', position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f4f7f7', margin: 0 }}>Synthesize Personas</h3>
                <p style={{ fontSize: '0.78rem', color: '#8D9999', margin: '4px 0 0 0' }}>Dataset: {generatingDataset.name}</p>
              </div>
              <button onClick={() => setIsGenerateModalOpen(false)} style={{ background: 'transparent', border: 'none', color: '#8D9999', cursor: 'pointer' }}><X size={18} /></button>
            </div>

            {generationRun ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ background: 'rgba(20, 184, 166, 0.1)', border: '1px solid rgba(20, 184, 166, 0.3)', borderRadius: '10px', padding: '14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#14B8A6', fontWeight: 600, fontSize: '0.88rem' }}>
                    <CheckCircle2 size={16} /> Synthesis Complete
                  </div>
                  <p style={{ fontSize: '0.8rem', color: '#8D9999', margin: '6px 0 0 0' }}>
                    Generated {generationRun.generated_count} personas ({generationRun.valid_count} valid, {generationRun.warning_count} warnings).
                  </p>
                </div>
                <button
                  onClick={() => setIsGenerateModalOpen(false)}
                  style={{ background: '#14B8A6', border: 'none', borderRadius: '8px', padding: '10px', color: '#080A0A', fontWeight: 600, cursor: 'pointer' }}
                >
                  Close & View in Persona Library
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Target Personas Count</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={personaCount}
                    onChange={(e) => setPersonaCount(Number(e.target.value))}
                    style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '8px 12px', color: '#f4f7f7', fontSize: '0.86rem' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Business Context</label>
                  <input
                    type="text"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '8px 12px', color: '#f4f7f7', fontSize: '0.86rem' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#8D9999', marginBottom: '6px' }}>Hypothesis / Value Proposition</label>
                  <textarea
                    rows={2}
                    value={businessDesc}
                    onChange={(e) => setBusinessDesc(e.target.value)}
                    style={{ width: '100%', background: '#111616', border: '1px solid #202727', borderRadius: '8px', padding: '8px 12px', color: '#f4f7f7', fontSize: '0.86rem', resize: 'vertical' }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                  <button
                    type="button"
                    onClick={() => setIsGenerateModalOpen(false)}
                    style={{ background: 'transparent', border: '1px solid #202727', borderRadius: '8px', padding: '8px 16px', color: '#8D9999', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleGeneratePersonas}
                    disabled={generating}
                    style={{ background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)', border: 'none', borderRadius: '8px', padding: '9px 18px', color: '#080A0A', fontWeight: 600, cursor: generating ? 'not-allowed' : 'pointer' }}
                  >
                    {generating ? 'Synthesizing...' : 'Generate Personas'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* LLM Gateway / OpenRouter Diagnostics Modal */}
      <OpenRouterDiagnosticModal isOpen={isOpenRouterModalOpen} onClose={() => setIsOpenRouterModalOpen(false)} />
    </div>
  );
};
