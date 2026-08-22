import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Business } from '../types';

interface BusinessSetupViewProps {
  onSelectBusiness?: (businessId: string) => void;
}

export const BusinessSetupView: React.FC<BusinessSetupViewProps> = ({ onSelectBusiness }) => {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [industry, setIndustry] = useState('');
  const [targetMarket, setTargetMarket] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchBusinesses = async () => {
    setLoading(true);
    const data = await api.getBusinesses();
    setBusinesses(data);
    setLoading(false);
  };

  useEffect(() => {
    fetchBusinesses();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !description) return;
    setSubmitting(true);
    await api.createBusiness({
      name,
      description,
      industry: industry || 'Technology',
      target_market: targetMarket || 'General Audience',
    });
    setSubmitting(false);
    setShowModal(false);
    setName('');
    setDescription('');
    setIndustry('');
    setTargetMarket('');
    fetchBusinesses();
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', color: '#fff' }}>Business & Commercial Profiles</h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Each synthetic persona is grounded in a specific business context, market segment, and value proposition.
          </p>
        </div>

        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <span>+</span> Create Business
        </button>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading business contexts...</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '20px' }}>
          {businesses.map((biz) => (
            <div
              key={biz.id}
              className="glass-panel"
              style={{
                padding: '24px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                  <h3 style={{ fontSize: '1.1rem', color: '#fff' }}>{biz.name}</h3>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      padding: '3px 8px',
                      borderRadius: '6px',
                      background: 'rgba(99, 102, 241, 0.15)',
                      color: '#a5b4fc',
                      fontWeight: 600,
                    }}
                  >
                    {biz.industry}
                  </span>
                </div>

                <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: '16px' }}>
                  {biz.description}
                </p>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '8px' }}>
                  <strong>Target Market:</strong> <span style={{ color: 'var(--text-muted)' }}>{biz.target_market}</span>
                </div>
              </div>

              <div
                style={{
                  paddingTop: '16px',
                  borderTop: '1px solid var(--border-subtle)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontSize: '0.78rem', color: '#34d399', fontWeight: 600 }}>
                  🧬 {biz.persona_count} Synthetic Personas
                </span>

                <button
                  className="btn btn-secondary"
                  style={{ fontSize: '0.78rem', padding: '6px 12px' }}
                  onClick={() => onSelectBusiness && onSelectBusiness(biz.id)}
                >
                  Generate Personas →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            className="glass-panel"
            style={{
              width: '100%',
              maxWidth: '540px',
              padding: '28px',
              backgroundColor: '#0c1222',
              borderRadius: '14px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: '1.15rem', color: '#fff', marginBottom: '18px' }}>Create New Business Context</h3>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Business Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. NovaFlow Financial"
                  className="form-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Industry / Domain *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Fintech, HealthTech, B2B SaaS"
                  className="form-input"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Business Description & Value Proposition *
                </label>
                <textarea
                  required
                  rows={3}
                  placeholder="Describe what the product does and the core problems it solves..."
                  className="form-textarea"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Target Market Segment *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. US delivery couriers, rideshare drivers (Ages 22-45)"
                  className="form-input"
                  value={targetMarket}
                  onChange={(e) => setTargetMarket(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Creating...' : 'Save Business'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
