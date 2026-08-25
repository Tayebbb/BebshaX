import React, { useState, useEffect } from 'react';
import { api } from '../../../services/api';
import { DatasetSource, DatasetSegment, PersonaGenerationRun } from '../../../types/dataset';
import { OpenRouterDiagnosticModal } from './OpenRouterDiagnosticModal';
import {
  Database,
  Plus,
  RefreshCw,
  Trash2,
  Eye,
  Users,
  FileSpreadsheet,
  Link,
  Upload,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  BarChart3,
  Layers,
  ArrowRight,
  Shield,
  Clock,
  Sparkles,
  Info,
  X,
  Cpu,
} from 'lucide-react';

export const DatasetSourcesView: React.FC = () => {
  const [datasets, setDatasets] = useState<DatasetSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDataset, setSelectedDataset] = useState<DatasetSource | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'schema' | 'stats' | 'segments'>('overview');

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
  const [datasetType, setDatasetType] = useState('csv');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Persona Generation State
  const [personaCount, setPersonaCount] = useState(10);
  const [businessName, setBusinessName] = useState('BebshaX Market Validation');
  const [businessDesc, setBusinessDesc] = useState('Evidence-grounded user demand testing');
  const [generating, setGenerating] = useState(false);
  const [generationRun, setGenerationRun] = useState<PersonaGenerationRun | null>(null);

  useEffect(() => {
    loadDatasets();
  }, []);

  const loadDatasets = async () => {
    setLoading(true);
    try {
      const data = await api.listDatasets();
      setDatasets(data);
    } catch (err) {
      console.error('Failed to load datasets:', err);
    } finally {
      setLoading(false);
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

      const created = await api.uploadDataset(formData);
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
      const refreshed = await api.refreshDataset(id);
      setDatasets(datasets.map((d) => (d.id === id ? refreshed : d)));
      if (selectedDataset?.id === id) setSelectedDataset(refreshed);
    } catch (err) {
      console.error('Failed to refresh dataset:', err);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to remove this dataset source?')) return;
    try {
      await api.deleteDataset(id);
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

  const totalRows = datasets.reduce((acc, d) => acc + (d.row_count || 0), 0);
  const totalSegments = datasets.reduce((acc, d) => acc + (d.segments?.length || 0), 0);
  const totalPersonasGen = datasets.reduce((acc, d) => acc + (d.persona_count_generated || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', color: '#fff', width: '100%', maxWidth: '1280px', margin: '0 auto', padding: '10px 0 60px 0' }}>
      {/* Top Header & Actions */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '10px', background: 'rgba(246, 200, 120, 0.15)', border: '1px solid rgba(246, 200, 120, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#f6c878' }}>
              <Database size={20} />
            </div>
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
              Dataset Sources & Empirical Grounding
            </h1>
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: '#9ca3af', maxWidth: '720px' }}>
            Connect public data URLs or upload research datasets to deterministically extract market segments, calculate demographic distributions, and generate evidence-constrained personas.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={() => setIsOpenRouterModalOpen(true)}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '9px',
              padding: '9px 16px',
              color: '#cbd5e1',
              fontSize: '0.86rem',
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s',
            }}
          >
            <Cpu size={16} color="#60a5fa" />
            OpenRouter Diagnostics
          </button>

          <button
            onClick={() => {
              resetForm();
              setIsAddModalOpen(true);
            }}
            style={{
              background: 'linear-gradient(135deg, #f6c878 0%, #e5a93c 100%)',
              border: 'none',
              borderRadius: '9px',
              padding: '9px 18px',
              color: '#000',
              fontSize: '0.86rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 14px rgba(246, 200, 120, 0.3)',
            }}
          >
            <Plus size={16} />
            Add Dataset
          </button>
        </div>
      </div>

      {/* Metrics Banner */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '12px', padding: '18px 20px' }}>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Connected Datasets</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f6c878' }}>{datasets.length}</div>
        </div>
        <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '12px', padding: '18px 20px' }}>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Profiled Evidence Rows</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#60a5fa' }}>{totalRows.toLocaleString()}</div>
        </div>
        <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '12px', padding: '18px 20px' }}>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Discovered Segments</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#4ade80' }}>{totalSegments}</div>
        </div>
        <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '12px', padding: '18px 20px' }}>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>Grounded Personas Synthesized</div>
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: '#c084fc' }}>{totalPersonasGen}</div>
        </div>
      </div>

      {/* Dataset Grid / Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <h2 style={{ fontSize: '1.15rem', fontWeight: 600, margin: 0, color: '#e2e8f0' }}>Dataset Repositories</h2>

        {loading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#9ca3af' }}>
            <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px auto' }} />
            Loading dataset sources...
          </div>
        ) : datasets.length === 0 ? (
          <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px dashed rgba(255, 255, 255, 0.15)', borderRadius: '16px', padding: '50px 20px', textAlign: 'center' }}>
            <Database size={36} color="#64748b" style={{ margin: '0 auto 14px auto' }} />
            <h3 style={{ margin: '0 0 8px 0', fontSize: '1.1rem', color: '#e2e8f0' }}>No datasets connected yet</h3>
            <p style={{ margin: '0 auto 20px auto', fontSize: '0.88rem', color: '#9ca3af', maxWidth: '480px' }}>
              Add a CSV, JSON, or TSV dataset URL or upload a file to enable evidence-grounded persona generation.
            </p>
            <button
              onClick={() => setIsAddModalOpen(true)}
              style={{
                background: '#f6c878',
                border: 'none',
                borderRadius: '8px',
                padding: '9px 18px',
                color: '#000',
                fontWeight: 600,
                fontSize: '0.86rem',
                cursor: 'pointer',
              }}
            >
              Add First Dataset
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '18px' }}>
            {datasets.map((ds) => (
              <div
                key={ds.id}
                onClick={() => setSelectedDataset(ds)}
                style={{
                  background: 'rgba(18, 20, 23, 0.7)',
                  border: selectedDataset?.id === ds.id ? '1px solid #f6c878' : '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '14px',
                  padding: '20px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  transition: 'all 0.2s ease',
                  position: 'relative',
                }}
              >
                {/* Card Header */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '8px',
                      background: ds.source_type === 'url' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                      border: `1px solid ${ds.source_type === 'url' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(34, 197, 94, 0.3)'}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: ds.source_type === 'url' ? '#60a5fa' : '#4ade80',
                    }}>
                      {ds.source_type === 'url' ? <Link size={16} /> : <FileSpreadsheet size={16} />}
                    </div>
                    <div>
                      <h4 style={{ margin: 0, fontSize: '0.96rem', fontWeight: 600, color: '#f8fafc' }}>
                        {ds.name}
                      </h4>
                      <span style={{ fontSize: '0.74rem', color: '#9ca3af' }}>
                        {ds.source_type === 'url' ? 'Public URL' : ds.original_file_name || 'Upload'} • {ds.file_type.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <span style={{
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: '6px',
                    background: ds.status === 'ready' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    color: ds.status === 'ready' ? '#4ade80' : '#f87171',
                  }}>
                    {ds.status.toUpperCase()}
                  </span>
                </div>

                {/* Description */}
                {ds.description && (
                  <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                    {ds.description}
                  </p>
                )}

                {/* Stats Bar */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', padding: '10px 12px', background: 'rgba(0, 0, 0, 0.3)', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontSize: '0.72rem', color: '#64748b' }}>ROWS</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#e2e8f0' }}>{ds.row_count.toLocaleString()}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.72rem', color: '#64748b' }}>SEGMENTS</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#4ade80' }}>{ds.segments?.length || 0}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.72rem', color: '#64748b' }}>PERSONAS</div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#c084fc' }}>{ds.persona_count_generated || 0}</div>
                  </div>
                </div>

                {/* Discovered Segments Chips */}
                {ds.segments && ds.segments.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {ds.segments.slice(0, 3).map((seg) => (
                      <span key={seg.id} style={{ fontSize: '0.72rem', background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '6px', padding: '2px 6px', color: '#cbd5e1' }}>
                        {seg.name} ({seg.population_percentage}%)
                      </span>
                    ))}
                    {ds.segments.length > 3 && (
                      <span style={{ fontSize: '0.72rem', color: '#64748b', alignSelf: 'center' }}>+{ds.segments.length - 3} more</span>
                    )}
                  </div>
                )}

                {/* Action Footer */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: '12px', marginTop: 'auto' }}>
                  <button
                    onClick={(e) => handleOpenGenerate(ds, e)}
                    style={{
                      background: 'rgba(246, 200, 120, 0.12)',
                      border: '1px solid rgba(246, 200, 120, 0.3)',
                      borderRadius: '6px',
                      padding: '5px 12px',
                      color: '#f6c878',
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                    }}
                  >
                    <Sparkles size={13} /> Generate Personas
                  </button>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {ds.source_type === 'url' && (
                      <button
                        title="Refresh dataset from URL"
                        onClick={(e) => handleRefresh(ds.id, e)}
                        style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: '4px' }}
                      >
                        <RefreshCw size={14} />
                      </button>
                    )}
                    <button
                      title="Delete dataset source"
                      onClick={(e) => handleDelete(ds.id, e)}
                      style={{ background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', padding: '4px' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dataset Detail View Modal */}
      {selectedDataset && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 90,
          padding: '20px',
        }}>
          <div style={{
            background: '#121417',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '880px',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            boxShadow: '0 25px 50px rgba(0, 0, 0, 0.7)',
          }}>
            {/* Header */}
            <div style={{ padding: '18px 24px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255, 255, 255, 0.02)' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600, color: '#fff' }}>{selectedDataset.name}</h3>
                <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>
                  {selectedDataset.source_type === 'url' ? selectedDataset.source_url : selectedDataset.original_file_name} • {selectedDataset.row_count.toLocaleString()} rows • {selectedDataset.column_count} columns
                </span>
              </div>
              <button
                onClick={() => setSelectedDataset(null)}
                style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: '6px' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', padding: '0 24px', gap: '20px' }}>
              {(['overview', 'schema', 'stats', 'segments'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    borderBottom: activeTab === tab ? '2px solid #f6c878' : '2px solid transparent',
                    color: activeTab === tab ? '#f6c878' : '#9ca3af',
                    fontWeight: activeTab === tab ? 600 : 400,
                    fontSize: '0.86rem',
                    padding: '12px 4px',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {tab === 'stats' ? 'Descriptive Statistics' : tab === 'segments' ? `Discovered Segments (${selectedDataset.segments?.length || 0})` : tab}
                </button>
              ))}
            </div>

            {/* Content Area */}
            <div style={{ padding: '24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {activeTab === 'overview' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '10px', padding: '16px' }}>
                    <div style={{ fontSize: '0.84rem', color: '#9ca3af', marginBottom: '8px' }}>Description</div>
                    <div style={{ fontSize: '0.9rem', color: '#e2e8f0', lineHeight: 1.5 }}>
                      {selectedDataset.description || 'No description provided.'}
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                    <div style={{ background: 'rgba(0,0,0,0.3)', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>PROVENANCE TYPE</div>
                      <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#cbd5e1' }}>{selectedDataset.source_type.toUpperCase()}</div>
                    </div>
                    <div style={{ background: 'rgba(0,0,0,0.3)', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>LAST PROCESSED</div>
                      <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#cbd5e1' }}>
                        {selectedDataset.last_processed_at ? new Date(selectedDataset.last_processed_at).toLocaleString() : 'Just now'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'schema' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ fontSize: '0.84rem', color: '#9ca3af' }}>Inferred Column Types & Quality Profiling</div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: '#9ca3af' }}>
                          <th style={{ padding: '8px 12px' }}>Column</th>
                          <th style={{ padding: '8px 12px' }}>Type</th>
                          <th style={{ padding: '8px 12px' }}>Missing Rate</th>
                          <th style={{ padding: '8px 12px' }}>Distinct Values</th>
                          <th style={{ padding: '8px 12px' }}>Sample Values</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedDataset.schema_metadata?.columns?.map((col) => (
                          <tr key={col.name} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                            <td style={{ padding: '10px 12px', fontWeight: 600, color: '#f8fafc' }}>{col.name}</td>
                            <td style={{ padding: '10px 12px' }}>
                              <span style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '0.72rem',
                                background: col.type === 'numeric' ? 'rgba(96, 165, 250, 0.15)' : col.type === 'categorical' ? 'rgba(74, 222, 128, 0.15)' : 'rgba(255, 255, 255, 0.08)',
                                color: col.type === 'numeric' ? '#60a5fa' : col.type === 'categorical' ? '#4ade80' : '#cbd5e1',
                              }}>
                                {col.type}
                              </span>
                            </td>
                            <td style={{ padding: '10px 12px', color: col.missing_percentage > 10 ? '#f87171' : '#9ca3af' }}>
                              {col.missing_percentage}%
                            </td>
                            <td style={{ padding: '10px 12px', color: '#e2e8f0' }}>{col.unique_count}</td>
                            <td style={{ padding: '10px 12px', color: '#94a3b8' }}>
                              {col.sample_values?.slice(0, 3).join(', ') || 'N/A'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeTab === 'stats' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  {/* Numeric Stats */}
                  {selectedDataset.statistics?.numeric && Object.keys(selectedDataset.statistics.numeric).length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '0.9rem', color: '#60a5fa', margin: '0 0 10px 0' }}>Numeric Distributions</h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                        {Object.entries(selectedDataset.statistics.numeric).map(([colName, stat]) => (
                          <div key={colName} style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '12px' }}>
                            <div style={{ fontWeight: 600, fontSize: '0.86rem', color: '#e2e8f0', marginBottom: '6px' }}>{colName}</div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', fontSize: '0.78rem' }}>
                              <div><span style={{ color: '#64748b' }}>Min:</span> {stat.min}</div>
                              <div><span style={{ color: '#64748b' }}>Median:</span> <strong style={{ color: '#f6c878' }}>{stat.median}</strong></div>
                              <div><span style={{ color: '#64748b' }}>Max:</span> {stat.max}</div>
                              <div><span style={{ color: '#64748b' }}>Mean:</span> {stat.mean}</div>
                              <div><span style={{ color: '#64748b' }}>Std:</span> {stat.std}</div>
                              <div><span style={{ color: '#64748b' }}>IQR:</span> {stat.iqr}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Categorical Stats */}
                  {selectedDataset.statistics?.categorical && Object.keys(selectedDataset.statistics.categorical).length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '0.9rem', color: '#4ade80', margin: '0 0 10px 0' }}>Categorical Frequencies</h4>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                        {Object.entries(selectedDataset.statistics.categorical).map(([colName, cat]) => (
                          <div key={colName} style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '8px', padding: '12px' }}>
                            <div style={{ fontWeight: 600, fontSize: '0.86rem', color: '#e2e8f0', marginBottom: '8px' }}>{colName}</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                              {cat.top_categories?.slice(0, 5).map((tc) => (
                                <div key={tc.category}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', marginBottom: '2px' }}>
                                    <span style={{ color: '#cbd5e1' }}>{tc.category}</span>
                                    <span style={{ color: '#4ade80', fontWeight: 600 }}>{tc.percentage}% ({tc.count})</span>
                                  </div>
                                  <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                                    <div style={{ width: `${tc.percentage}%`, height: '100%', background: '#4ade80', borderRadius: '2px' }} />
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

              {activeTab === 'segments' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ fontSize: '0.84rem', color: '#9ca3af' }}>
                    Mathematically derived segments based on feature distributions. Personas will be synthesized according to these exact population share quotas.
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '14px' }}>
                    {selectedDataset.segments?.map((seg) => (
                      <div key={seg.id} style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.92rem', color: '#f6c878' }}>{seg.name}</span>
                          <span style={{ fontSize: '0.78rem', background: 'rgba(246,200,120,0.15)', color: '#f6c878', padding: '2px 8px', borderRadius: '6px', fontWeight: 600 }}>
                            {seg.population_percentage}% Share
                          </span>
                        </div>

                        {seg.constraints?.rule_description && (
                          <div style={{ fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                            {seg.constraints.rule_description}
                          </div>
                        )}

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '0.78rem', background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '6px' }}>
                          <div>
                            <span style={{ color: '#64748b' }}>Age Range:</span> {seg.constraints?.age_range ? `${seg.constraints.age_range[0]}–${seg.constraints.age_range[1]}` : 'N/A'}
                          </div>
                          <div>
                            <span style={{ color: '#64748b' }}>Monthly Budget:</span> ~৳{seg.constraints?.monthly_budget?.median || 'N/A'}
                          </div>
                          <div>
                            <span style={{ color: '#64748b' }}>Tech Familiarity:</span> {seg.constraints?.technology_familiarity || 'Medium'}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255, 255, 255, 0.02)' }}>
              <button
                onClick={() => setSelectedDataset(null)}
                style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '8px 16px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.84rem' }}
              >
                Close
              </button>

              <button
                onClick={(e) => handleOpenGenerate(selectedDataset, e)}
                style={{
                  background: 'linear-gradient(135deg, #f6c878 0%, #e5a93c 100%)',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '9px 18px',
                  color: '#000',
                  fontWeight: 600,
                  fontSize: '0.84rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <Sparkles size={15} /> Generate Evidence Personas
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Dataset Modal */}
      {isAddModalOpen && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100,
          padding: '20px',
        }}>
          <div style={{
            background: '#121417',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '560px',
            overflow: 'hidden',
          }}>
            {/* Header */}
            <div style={{ padding: '18px 24px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Database size={18} color="#f6c878" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600 }}>Add Dataset Source</h3>
              </div>
              <button onClick={() => setIsAddModalOpen(false)} style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            {/* Mode Switcher */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', padding: '12px 24px 0 24px', gap: '10px' }}>
              <button
                type="button"
                onClick={() => setAddMode('url')}
                style={{
                  background: addMode === 'url' ? 'rgba(246, 200, 120, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: addMode === 'url' ? '1px solid #f6c878' : '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                  padding: '8px',
                  color: addMode === 'url' ? '#f6c878' : '#9ca3af',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <Link size={14} /> Dataset URL
              </button>
              <button
                type="button"
                onClick={() => setAddMode('upload')}
                style={{
                  background: addMode === 'upload' ? 'rgba(246, 200, 120, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                  border: addMode === 'upload' ? '1px solid #f6c878' : '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                  padding: '8px',
                  color: addMode === 'upload' ? '#f6c878' : '#9ca3af',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <Upload size={14} /> Upload File
              </button>
            </div>

            {/* Form */}
            <form onSubmit={addMode === 'url' ? handleCreateUrl : handleUploadFile} style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                  Dataset Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Bangladesh Student Budget Survey 2026"
                  value={datasetName}
                  onChange={(e) => setDatasetName(e.target.value)}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '10px 12px', color: '#fff', fontSize: '0.86rem', outline: 'none' }}
                />
              </div>

              {addMode === 'url' ? (
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                    Dataset URL (HTTP/HTTPS) *
                  </label>
                  <input
                    type="url"
                    required
                    placeholder="https://example.com/data/survey.csv"
                    value={datasetUrl}
                    onChange={(e) => setDatasetUrl(e.target.value)}
                    style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '10px 12px', color: '#fff', fontSize: '0.86rem', outline: 'none' }}
                  />
                  <div style={{ fontSize: '0.74rem', color: '#64748b', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Shield size={12} color="#4ade80" /> Protected by server-side SSRF screening and size limiters.
                  </div>
                </div>
              ) : (
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                    Dataset File (CSV, JSON, TSV, XLSX) *
                  </label>
                  <input
                    type="file"
                    required
                    accept=".csv,.json,.jsonl,.tsv,.xlsx"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '8px 12px', color: '#cbd5e1', fontSize: '0.82rem', outline: 'none' }}
                  />
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                    File Format
                  </label>
                  <select
                    value={datasetType}
                    onChange={(e) => setDatasetType(e.target.value)}
                    style={{ width: '100%', background: '#1c1f24', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '10px 12px', color: '#fff', fontSize: '0.86rem', outline: 'none' }}
                  >
                    <option value="csv">CSV (Comma-separated)</option>
                    <option value="json">JSON (Object Array)</option>
                    <option value="tsv">TSV (Tab-separated)</option>
                    <option value="xlsx">Excel (XLSX)</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                  Description (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="Context on how the data was gathered..."
                  value={datasetDesc}
                  onChange={(e) => setDatasetDesc(e.target.value)}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '8px 12px', color: '#fff', fontSize: '0.84rem', outline: 'none', resize: 'none' }}
                />
              </div>

              {formError && (
                <div style={{ padding: '10px 12px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', fontSize: '0.82rem' }}>
                  {formError}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '8px 16px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.84rem' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    background: '#f6c878',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '9px 20px',
                    color: '#000',
                    fontWeight: 600,
                    fontSize: '0.84rem',
                    cursor: submitting ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {submitting ? <RefreshCw size={14} className="animate-spin" /> : null}
                  {submitting ? 'Profiling Dataset...' : 'Ingest & Profile'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Generate Grounded Personas Modal */}
      {isGenerateModalOpen && generatingDataset && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100,
          padding: '20px',
        }}>
          <div style={{
            background: '#121417',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '680px',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <div style={{ padding: '18px 24px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="#f6c878" />
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600 }}>Evidence-Grounded Persona Synthesis</h3>
              </div>
              <button onClick={() => setIsGenerateModalOpen(false)} style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {/* Grounded Distribution Table */}
              <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '10px', padding: '14px' }}>
                <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                  Mathematical Segment Allocation ({personaCount} personas total)
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {generatingDataset.segments?.map((seg) => {
                    const allocated = Math.max(1, Math.round(seg.population_share * personaCount));
                    return (
                      <div key={seg.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.82rem' }}>
                        <span style={{ color: '#cbd5e1' }}>{seg.name} ({seg.population_percentage}%)</span>
                        <span style={{ fontWeight: 600, color: '#f6c878' }}>{allocated} personas</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                  Persona Count (1–20)
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={personaCount}
                  onChange={(e) => setPersonaCount(Math.min(20, Math.max(1, parseInt(e.target.value) || 1)))}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '10px 12px', color: '#fff', fontSize: '0.86rem', outline: 'none' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#cbd5e1', marginBottom: '6px', fontWeight: 500 }}>
                  Target Business / Product Initiative
                </label>
                <input
                  type="text"
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '10px 12px', color: '#fff', fontSize: '0.86rem', outline: 'none' }}
                />
              </div>

              {/* Generation Report (when ready) */}
              {generationRun && (
                <div style={{ background: 'rgba(34, 197, 94, 0.06)', border: '1px solid rgba(34, 197, 94, 0.25)', borderRadius: '12px', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#4ade80' }}>
                      ✓ Generated {generationRun.generated_count} Personas
                    </span>
                    <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>
                      Model: {generationRun.model_used.split('/').pop()}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: '12px', fontSize: '0.8rem' }}>
                    <span style={{ color: '#4ade80' }}>Valid: {generationRun.valid_count}</span>
                    <span style={{ color: '#facc15' }}>Warnings: {generationRun.warning_count}</span>
                    <span style={{ color: '#f87171' }}>Contradictions: {generationRun.contradiction_count}</span>
                  </div>

                  <div style={{ maxHeight: '180px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {generationRun.personas.map((p, idx) => (
                      <div key={idx} style={{ background: 'rgba(0,0,0,0.3)', padding: '8px 12px', borderRadius: '6px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div>
                          <strong style={{ color: '#f8fafc' }}>{p.name}</strong> ({p.age} yrs • {p.occupation})
                        </div>
                        <span style={{
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: p.validation?.status === 'VALID' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: p.validation?.status === 'VALID' ? '#4ade80' : '#facc15',
                        }}>
                          {p.validation?.status || 'VALID'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                onClick={() => setIsGenerateModalOpen(false)}
                style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '8px 16px', color: '#9ca3af', cursor: 'pointer', fontSize: '0.84rem' }}
              >
                {generationRun ? 'Done' : 'Cancel'}
              </button>

              <button
                type="button"
                disabled={generating}
                onClick={handleGeneratePersonas}
                style={{
                  background: 'linear-gradient(135deg, #f6c878 0%, #e5a93c 100%)',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '9px 20px',
                  color: '#000',
                  fontWeight: 600,
                  fontSize: '0.84rem',
                  cursor: generating ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                {generating ? <RefreshCw size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {generating ? 'Synthesizing Personas...' : 'Start Persona Synthesis'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* OpenRouter Diagnostic Panel Modal */}
      <OpenRouterDiagnosticModal
        isOpen={isOpenRouterModalOpen}
        onClose={() => setIsOpenRouterModalOpen(false)}
      />
    </div>
  );
};
