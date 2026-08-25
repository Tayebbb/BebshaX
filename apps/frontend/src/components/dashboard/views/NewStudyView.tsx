import React, { useState } from 'react';
import {
  Users,
  Compass,
  MessageSquare,
  BadgePercent,
  ArrowUp,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { StudyType } from '../../../types';

interface NewStudyViewProps {
  onStartStudy: (type: StudyType, initialPrompt?: string) => Promise<void> | void;
}

export const NewStudyView: React.FC<NewStudyViewProps> = ({ onStartStudy }) => {
  const [prompt, setPrompt] = useState('');
  const [selectedType, setSelectedType] = useState<StudyType>('interviews');
  const [isFocused, setIsFocused] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cleanPrompt = prompt.trim();

    if (!cleanPrompt) {
      setValidationError('Describe your product idea before starting the study.');
      return;
    }

    setValidationError(null);
    setIsSubmitting(true);
    try {
      await onStartStudy(selectedType, cleanPrompt);
    } catch {
      setIsSubmitting(false);
    }
  };

  const handleCardClick = async (type: StudyType) => {
    setSelectedType(type);
    setValidationError(null);
    const cleanPrompt = prompt.trim();
    if (cleanPrompt) {
      setIsSubmitting(true);
      try {
        await onStartStudy(type, cleanPrompt);
      } catch {
        setIsSubmitting(false);
      }
    }
  };

  const studyTypes: {
    type: StudyType;
    icon: React.ReactNode;
    iconBg: string;
    iconColor: string;
    title: string;
    description: string;
  }[] = [
    {
      type: 'interviews',
      icon: <Users size={19} />,
      iconBg: 'rgba(99, 102, 241, 0.15)',
      iconColor: '#818CF8',
      title: 'User Interviews',
      description: 'Simulate in-depth discovery interviews with grounded personas to reveal daily workflows and unarticulated pain points.',
    },
    {
      type: 'landing_page_test',
      icon: <Compass size={19} />,
      iconBg: 'rgba(56, 189, 248, 0.15)',
      iconColor: '#38BDF8',
      title: 'Concept & Demand',
      description: 'Validate product-market fit, value proposition desirability, and core feature hypotheses before writing code.',
    },
    {
      type: 'message_testing',
      icon: <MessageSquare size={19} />,
      iconBg: 'rgba(167, 139, 250, 0.15)',
      iconColor: '#A78BFA',
      title: 'Message Testing',
      description: 'Test pitch clarity, value proposition framing, and objection handling across customer demographic segments.',
    },
    {
      type: 'ab_test',
      icon: <BadgePercent size={19} />,
      iconBg: 'rgba(236, 72, 153, 0.15)',
      iconColor: '#F472B6',
      title: 'Pricing & WTP',
      description: 'Validate price elasticity, subscription ceilings, and tier packaging against grounded budget constraints.',
    },
  ];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 'calc(100vh - 120px)',
        padding: '30px 24px',
        maxWidth: '1080px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* Title & Subtitle */}
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <h1
          style={{
            fontSize: 'clamp(2.1rem, 3.5vw, 2.85rem)',
            fontWeight: 600,
            color: '#FFFFFF',
            letterSpacing: '-0.03em',
            margin: '0 0 10px 0',
            lineHeight: 1.2,
          }}
        >
          What do you want to find out?
        </h1>
        <p
          style={{
            fontSize: '0.98rem',
            color: '#9CA3AF',
            margin: 0,
            letterSpacing: '-0.01em',
          }}
        >
          Ask anything about your business idea, or pick any study type below.
        </p>
      </div>

      {/* Validation Error Banner */}
      {validationError && (
        <div
          role="alert"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '10px',
            padding: '10px 16px',
            color: '#F87171',
            fontSize: '0.86rem',
            marginBottom: '16px',
            width: '100%',
            maxWidth: '1040px',
          }}
        >
          <AlertCircle size={16} style={{ flexShrink: 0 }} />
          <span>{validationError}</span>
        </div>
      )}

      {/* Wide Query Input Card */}
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: '1040px',
          background: 'rgba(18, 21, 28, 0.65)',
          border: isFocused
            ? '1px solid rgba(99, 102, 241, 0.5)'
            : '1px solid #1E2330',
          borderRadius: '20px',
          padding: '20px 24px',
          position: 'relative',
          boxShadow: isFocused
            ? '0 16px 40px -10px rgba(0, 0, 0, 0.7), 0 0 24px rgba(99, 102, 241, 0.18)'
            : '0 12px 36px -10px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(16px)',
          marginBottom: '28px',
          transition: 'all 0.2s ease',
        }}
      >
        <textarea
          rows={3}
          value={prompt}
          disabled={isSubmitting}
          onChange={(e) => {
            setPrompt(e.target.value);
            if (validationError && e.target.value.trim()) setValidationError(null);
          }}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Describe your business idea, target audience, or pricing hypothesis (e.g., An AI study planner for students with a 250 BDT/month tier)..."
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          style={{
            width: '100%',
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: '#FFFFFF',
            fontSize: '1.05rem',
            lineHeight: 1.55,
            resize: 'none',
            fontFamily: 'inherit',
            paddingRight: '60px',
          }}
        />

        {/* Submit Arrow / Loading Button */}
        <button
          type="submit"
          disabled={isSubmitting || !prompt.trim()}
          aria-label={isSubmitting ? 'Creating study...' : 'Start research study'}
          style={{
            position: 'absolute',
            bottom: '18px',
            right: '20px',
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            background: prompt.trim()
              ? 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)'
              : 'rgba(255, 255, 255, 0.06)',
            border: 'none',
            color: prompt.trim() ? '#FFFFFF' : '#4B5563',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: prompt.trim() && !isSubmitting ? 'pointer' : 'default',
            transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
            boxShadow: prompt.trim() ? '0 4px 14px rgba(99, 102, 241, 0.4)' : 'none',
          }}
        >
          {isSubmitting ? (
            <Loader2 size={19} className="animate-spin" />
          ) : (
            <ArrowUp size={19} strokeWidth={2.5} />
          )}
        </button>
      </form>

      {/* 4 Study Type Quick Select Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
          gap: '14px',
          width: '100%',
          maxWidth: '1040px',
        }}
      >
        {studyTypes.map((item) => {
          const isSelected = selectedType === item.type;
          return (
            <div
              key={item.type}
              onClick={() => handleCardClick(item.type)}
              style={{
                background: isSelected
                  ? 'rgba(99, 102, 241, 0.06)'
                  : 'rgba(18, 21, 28, 0.45)',
                border: isSelected
                  ? '1px solid rgba(99, 102, 241, 0.45)'
                  : '1px solid #1E2330',
                borderRadius: '16px',
                padding: '20px 18px',
                cursor: 'pointer',
                transition: 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                position: 'relative',
                boxShadow: isSelected ? '0 4px 16px rgba(99, 102, 241, 0.12)' : 'none',
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.3)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = '#1E2330';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.background = 'rgba(18, 21, 28, 0.45)';
                }
              }}
            >
              {/* Icon */}
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: item.iconBg,
                  color: item.iconColor,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                {item.icon}
              </div>

              {/* Text */}
              <div>
                <h2
                  style={{
                    fontSize: '0.92rem',
                    fontWeight: 600,
                    color: '#FFFFFF',
                    margin: '0 0 6px 0',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {item.title}
                </h2>
                <p
                  style={{
                    fontSize: '0.78rem',
                    color: '#8A909A',
                    margin: 0,
                    lineHeight: 1.45,
                  }}
                >
                  {item.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
