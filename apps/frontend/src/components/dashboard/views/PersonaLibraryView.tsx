import React, { useState, useEffect } from 'react';
import {
  Users,
  Search,
  Plus,
  Sparkles,
  ShieldCheck,
  Brain,
  MessageSquare,
  ChevronRight,
  Filter,
  Layers,
  Award,
} from 'lucide-react';
import { Persona } from '../../../types';
import { api } from '../../../services/api';

interface PersonaLibraryViewProps {
  onStartInterviewWithPersona?: (personaId: string) => void;
}

export const PersonaLibraryView: React.FC<PersonaLibraryViewProps> = ({
  onStartInterviewWithPersona,
}) => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndustry, setSelectedIndustry] = useState<string>('all');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [targetSegment, setTargetSegment] = useState('');
  const [demographicKeywords, setDemographicKeywords] = useState('');
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null);

  useEffect(() => {
    const loadPersonas = async () => {
      try {
        const data = await api.getPersonas();
        setPersonas(data);
      } catch {
        // fallback
      }
    };
    loadPersonas();
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetSegment.trim()) return;

    try {
      setIsGenerating(true);
      const keywords = demographicKeywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean);
      const result = await api.generatePersona(
        'biz_fintech_01',
        targetSegment.trim(),
        keywords.length > 0 ? keywords : ['Budget Conscious', 'Fast Delivery', 'Mobile First']
      );
      setPersonas((prev) => [result.persona, ...prev]);
      setShowGenerateModal(false);
      setTargetSegment('');
      setDemographicKeywords('');
    } catch {
      // ignore
    } finally {
      setIsGenerating(false);
    }
  };

  const filteredPersonas = personas.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.archetype.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.demographics.occupation.toLowerCase().includes(searchQuery.toLowerCase());

    return matchesSearch;
  });

  return (
    <div
      style={{
        padding: '32px 40px',
        maxWidth: '1200px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.85rem',
              fontWeight: 500,
              color: '#FFFFFF',
              letterSpacing: '-0.02em',
              margin: '0 0 6px 0',
            }}
          >
            Persona Library
          </h1>
          <p style={{ fontSize: '0.9rem', color: '#9CA3AF', margin: 0 }}>
            Saved personas and audiences you can reuse in any study.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowGenerateModal(true)}
          style={{
            background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
            color: '#080909',
            border: 'none',
            borderRadius: '10px',
            padding: '9px 18px',
            fontSize: '0.86rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            cursor: 'pointer',
            boxShadow: '0 4px 14px rgba(246, 200, 120, 0.25)',
          }}
        >
          <Plus size={16} strokeWidth={2.5} />
          Generate Persona
        </button>
      </div>

      {/* Filter Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '28px',
          flexWrap: 'wrap',
        }}
      >
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
            placeholder="Search personas by name, role..."
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

        <div style={{ color: '#6B7280', fontSize: '0.82rem' }}>
          {filteredPersonas.length} personas grounded in empirical datasets
        </div>
      </div>

      {/* Personas Content / Empty State */}
      {filteredPersonas.length === 0 ? (
        /* Empty State matching Screenshot 3 */
        <div
          style={{
            width: '100%',
            border: '1px dashed rgba(255, 255, 255, 0.1)',
            borderRadius: '16px',
            padding: '64px 24px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            textAlign: 'center',
            background: 'rgba(255, 255, 255, 0.01)',
          }}
        >
          {/* Yellow stacked books icon ||\ */}
          <div
            style={{
              fontSize: '1.6rem',
              color: '#F6C878',
              letterSpacing: '2px',
              fontFamily: 'monospace',
              fontWeight: 700,
              marginBottom: '14px',
            }}
          >
            ||\
          </div>
          <div
            style={{
              fontSize: '1rem',
              fontWeight: 600,
              color: '#FFFFFF',
              marginBottom: '4px',
            }}
          >
            Your library is empty
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8A909A', maxWidth: '360px' }}>
            Save personas from any study to reuse them here.
          </div>
          <button
            type="button"
            onClick={() => setShowGenerateModal(true)}
            style={{
              marginTop: '18px',
              background: 'rgba(246, 200, 120, 0.12)',
              border: '1px solid rgba(246, 200, 120, 0.3)',
              color: '#F6C878',
              padding: '8px 16px',
              borderRadius: '8px',
              fontSize: '0.82rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            + Generate Your First Persona
          </button>
        </div>
      ) : (
        /* Persona Cards Grid */
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: '20px',
          }}
        >
          {filteredPersonas.map((persona) => {
            const isSelected = selectedPersona?.id === persona.id;
            return (
              <div
                key={persona.id}
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: isSelected
                    ? '1px solid rgba(246, 200, 120, 0.5)'
                    : '1px solid rgba(255, 255, 255, 0.07)',
                  borderRadius: '16px',
                  padding: '22px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  transition: 'all 0.2s ease',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'rgba(246, 200, 120, 0.35)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = isSelected
                    ? 'rgba(246, 200, 120, 0.5)'
                    : 'rgba(255, 255, 255, 0.07)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                {/* Persona Top Info */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div
                    style={{
                      width: '42px',
                      height: '42px',
                      borderRadius: '12px',
                      background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                      color: '#080909',
                      fontWeight: 700,
                      fontSize: '1rem',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {persona.name.charAt(0)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: '#FFFFFF', fontSize: '0.98rem' }}>
                      {persona.name}
                    </div>
                    <div style={{ color: '#9CA3AF', fontSize: '0.8rem' }}>
                      {persona.demographics.occupation} • {persona.demographics.location}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '6px',
                      background: 'rgba(16, 185, 129, 0.12)',
                      color: '#10B981',
                      border: '1px solid rgba(16, 185, 129, 0.25)',
                    }}
                  >
                    {Math.round(persona.grounding_ratio * 100)}% Grounded
                  </div>
                </div>

                {/* Tagline */}
                <div
                  style={{
                    fontSize: '0.84rem',
                    color: '#D1D5DB',
                    fontStyle: 'italic',
                    lineHeight: 1.4,
                  }}
                >
                  "{persona.tagline}"
                </div>

                {/* Attributes preview */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {persona.attributes.slice(0, 3).map((attr, idx) => (
                    <span
                      key={idx}
                      style={{
                        fontSize: '0.74rem',
                        padding: '3px 8px',
                        borderRadius: '6px',
                        background: 'rgba(255, 255, 255, 0.04)',
                        color: '#9CA3AF',
                        border: '1px solid rgba(255, 255, 255, 0.06)',
                      }}
                    >
                      {attr.title}
                    </span>
                  ))}
                </div>

                {/* Demographics row */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '0.78rem',
                    color: '#6B7280',
                    borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                    paddingTop: '12px',
                    marginTop: 'auto',
                  }}
                >
                  <span>Age {persona.demographics.age}</span>
                  <span>{persona.demographics.income_bracket}</span>
                  <span>Model: {persona.generation_model}</span>
                </div>

                {/* Action button */}
                {onStartInterviewWithPersona && (
                  <button
                    type="button"
                    onClick={() => onStartInterviewWithPersona(persona.id)}
                    style={{
                      width: '100%',
                      background: 'rgba(246, 200, 120, 0.08)',
                      border: '1px solid rgba(246, 200, 120, 0.25)',
                      color: '#F6C878',
                      borderRadius: '8px',
                      padding: '8px',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px',
                      marginTop: '4px',
                    }}
                  >
                    <MessageSquare size={14} /> Start Interview
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Generate Persona Modal */}
      {showGenerateModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(8px)',
            padding: '16px',
          }}
          onClick={() => setShowGenerateModal(false)}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '480px',
              background: '#0F1011',
              border: '1px solid rgba(246, 200, 120, 0.3)',
              borderRadius: '20px',
              padding: '28px',
              boxShadow: '0 24px 48px rgba(0, 0, 0, 0.6)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              style={{
                fontSize: '1.25rem',
                fontWeight: 600,
                color: '#FFFFFF',
                margin: '0 0 6px 0',
              }}
            >
              Generate Evidence-Grounded Persona
            </h2>
            <p style={{ fontSize: '0.82rem', color: '#9CA3AF', margin: '0 0 20px 0' }}>
              BebshaX PersonaEngine generates verified attributes anchored in empirical datasets with zero API budget.
            </p>

            <form onSubmit={handleGenerate}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#D1D5DB', marginBottom: '6px' }}>
                  Target Segment / Demographic Role *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Freelance Logistics Courier or B2B SaaS Buyer"
                  value={targetSegment}
                  onChange={(e) => setTargetSegment(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                    color: '#FFFFFF',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '0.82rem', color: '#D1D5DB', marginBottom: '6px' }}>
                  Focus Keywords / Traits (comma separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Price sensitive, Mobile heavy, High maintenance"
                  value={demographicKeywords}
                  onChange={(e) => setDemographicKeywords(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                    color: '#FFFFFF',
                    fontSize: '0.88rem',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={() => setShowGenerateModal(false)}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    color: '#9CA3AF',
                    padding: '8px 16px',
                    borderRadius: '8px',
                    fontSize: '0.84rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isGenerating}
                  style={{
                    background: 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)',
                    border: 'none',
                    color: '#080909',
                    padding: '8px 18px',
                    borderRadius: '8px',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: isGenerating ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isGenerating ? 'Synthesizing...' : 'Generate'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
