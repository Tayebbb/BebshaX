import React, { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { Conversation, ConversationTurn, Persona } from '../types';

interface InterviewChatViewProps {
  initialPersonaId?: string;
}

export const InterviewChatView: React.FC<InterviewChatViewProps> = ({ initialPersonaId }) => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>(initialPersonaId || 'per_sarah_01');
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);

  // New Objective modal
  const [showObjectiveModal, setShowObjectiveModal] = useState(false);
  const [newObjective, setNewObjective] = useState('');

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const perList = await api.getPersonas();
      setPersonas(perList);
      const targetId = initialPersonaId || (perList.length > 0 ? perList[0].id : 'per_sarah_01');
      setSelectedPersonaId(targetId);

      // Default to existing conversation or create new
      const conv = await api.getConversation('conv_201');
      if (conv && conv.persona_id === targetId) {
        setConversation(conv);
      } else {
        const fresh = await api.startConversation(
          targetId,
          'Evaluate reaction to automatic micro-tax withholding and emergency unlock policies.'
        );
        setConversation(fresh);
      }
      setLoading(false);
    };
    load();
  }, [initialPersonaId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation?.turns]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !conversation || sending) return;

    const message = inputText.trim();
    setInputText('');
    setSending(true);

    const result = await api.sendMessage(conversation.id, message);

    setConversation((prev) => {
      if (!prev) return null;
      return {
        ...prev,
        turns: [...prev.turns, result.userTurn, result.assistantTurn],
      };
    });

    setSending(false);
  };

  const handleStartNewConversation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newObjective) return;
    setLoading(true);
    const newConv = await api.startConversation(selectedPersonaId, newObjective);
    setConversation(newConv);
    setShowObjectiveModal(false);
    setNewObjective('');
    setLoading(false);
  };

  const selectedPersona = personas.find((p) => p.id === selectedPersonaId);

  const exportTranscript = () => {
    if (!conversation) return;
    const text = `# Interview Transcript: ${selectedPersona?.name || 'Persona'}
Objective: ${conversation.objective}
Date: ${new Date(conversation.created_at).toLocaleString()}

${conversation.turns
  .map(
    (t) =>
      `### ${t.role === 'user' ? 'Interviewer' : selectedPersona?.name || 'Persona'} (${new Date(t.timestamp).toLocaleTimeString()})
${t.content}
${t.served_by ? `*(Served by: ${t.served_by} in ${t.latency_ms}ms)*\n` : ''}`
  )
  .join('\n\n')}
`;
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `interview_${selectedPersona?.name.replace(/\s+/g, '_')}_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', height: 'calc(100vh - 140px)' }}>
      {/* Header Controls */}
      <div
        className="glass-panel"
        style={{
          padding: '14px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #6366f1 0%, #38bdf8 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
            }}
          >
            👤
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ fontSize: '1rem', color: '#fff' }}>{selectedPersona?.name}</h3>
              <span style={{ fontSize: '0.72rem', color: '#38bdf8' }}>({selectedPersona?.demographics.occupation})</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              Objective: <strong style={{ color: '#e2e8f0' }}>{conversation?.objective}</strong>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="btn btn-secondary" style={{ fontSize: '0.78rem' }} onClick={exportTranscript}>
            <span>📥</span> Export Transcript
          </button>

          <button className="btn btn-primary" style={{ fontSize: '0.78rem' }} onClick={() => setShowObjectiveModal(true)}>
            <span>+</span> New Scenario
          </button>
        </div>
      </div>

      {/* Main Chat Container */}
      <div
        className="glass-panel"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          backgroundColor: '#0c1222',
        }}
      >
        {/* Messages Scroll Area */}
        <div
          style={{
            flex: 1,
            padding: '24px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '18px',
          }}
        >
          {loading ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', margin: 'auto' }}>
              Initializing interview turn session...
            </div>
          ) : conversation?.turns.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', margin: 'auto' }}>
              <div style={{ fontSize: '2rem', marginBottom: '8px' }}>💬</div>
              <h4 style={{ color: '#fff', marginBottom: '4px' }}>Interview Session Started</h4>
              <p style={{ fontSize: '0.8rem' }}>
                Ask {selectedPersona?.name} questions to test product messaging, pricing, or feature trade-offs.
              </p>
            </div>
          ) : (
            conversation?.turns.map((turn: ConversationTurn) => {
              const isUser = turn.role === 'user';

              return (
                <div
                  key={turn.id}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: isUser ? 'flex-end' : 'flex-start',
                    maxWidth: '80%',
                    alignSelf: isUser ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.7rem',
                      color: 'var(--text-dim)',
                      marginBottom: '4px',
                      paddingLeft: '4px',
                      paddingRight: '4px',
                    }}
                  >
                    {isUser ? 'Interviewer (You)' : selectedPersona?.name} •{' '}
                    {new Date(turn.timestamp).toLocaleTimeString()}
                  </div>

                  <div
                    style={{
                      padding: '14px 18px',
                      borderRadius: isUser ? '14px 14px 2px 14px' : '14px 14px 14px 2px',
                      background: isUser
                        ? 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)'
                        : 'rgba(30, 41, 59, 0.85)',
                      border: isUser ? 'none' : '1px solid var(--border-subtle)',
                      color: '#fff',
                      fontSize: '0.88rem',
                      lineHeight: 1.6,
                      boxShadow: varShadow(isUser),
                    }}
                  >
                    {turn.content}
                  </div>

                  {/* Persona Turn Provenance & Memory Trace */}
                  {!isUser && turn.served_by && (
                    <div
                      style={{
                        marginTop: '6px',
                        display: 'flex',
                        flexWrap: 'wrap',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '0.68rem',
                        color: 'var(--text-dim)',
                      }}
                    >
                      <span className="mono" style={{ color: '#38bdf8' }}>
                        ⚡ {turn.served_by} ({turn.latency_ms}ms)
                      </span>

                      {turn.retrieved_memories && turn.retrieved_memories.length > 0 && (
                        <span style={{ color: '#c084fc' }}>
                          🧠 {turn.retrieved_memories.length} memories retrieved
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}

          {sending && (
            <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              <span className="pulse-dot" /> {selectedPersona?.name} is thinking (routing via conversation pool)...
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Chat Input Bar */}
        <form
          onSubmit={handleSend}
          style={{
            padding: '16px 20px',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: '12px',
            background: 'rgba(10, 15, 29, 0.9)',
          }}
        >
          <input
            type="text"
            className="form-input"
            style={{ flex: 1, padding: '12px 16px', fontSize: '0.9rem' }}
            placeholder={`Ask ${selectedPersona?.name || 'persona'} a question...`}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={sending}
          />

          <button type="submit" className="btn btn-primary" style={{ padding: '0 24px' }} disabled={sending || !inputText.trim()}>
            Send Turn →
          </button>
        </form>
      </div>

      {/* New Objective Modal */}
      {showObjectiveModal && (
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
          onClick={() => setShowObjectiveModal(false)}
        >
          <div
            className="glass-panel"
            style={{
              width: '100%',
              maxWidth: '520px',
              padding: '28px',
              backgroundColor: '#0c1222',
              borderRadius: '14px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: '1.15rem', color: '#fff', marginBottom: '14px' }}>Start New Interview Scenario</h3>

            <form onSubmit={handleStartNewConversation} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Select Persona
                </label>
                <select
                  className="form-select"
                  value={selectedPersonaId}
                  onChange={(e) => setSelectedPersonaId(e.target.value)}
                >
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.archetype})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Research Objective / Scenario Prompt *
                </label>
                <textarea
                  required
                  rows={3}
                  className="form-textarea"
                  placeholder="e.g. Test price tolerance for a $9.99/mo premium automated tax withholding service..."
                  value={newObjective}
                  onChange={(e) => setNewObjective(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowObjectiveModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Start Session
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

function varShadow(isUser: boolean) {
  return isUser ? '0 4px 12px rgba(79, 70, 229, 0.3)' : '0 4px 12px rgba(0, 0, 0, 0.4)';
}
