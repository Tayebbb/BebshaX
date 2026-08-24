import React, { useState } from 'react';
import {
  Users,
  Compass,
  MessageSquare,
  BadgePercent,
  ArrowUp,
} from 'lucide-react';
import { StudyType } from '../../../types';

interface NewStudyViewProps {
  onStartStudy: (type: StudyType, initialPrompt?: string) => void;
}

export const NewStudyView: React.FC<NewStudyViewProps> = ({ onStartStudy }) => {
  const [prompt, setPrompt] = useState('');
  const [selectedType, setSelectedType] = useState<StudyType>('interviews');
  const [isFocused, setIsFocused] = useState(false);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    onStartStudy(selectedType, prompt.trim() || undefined);
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
      iconBg: 'rgba(16, 185, 129, 0.12)',
      iconColor: '#10B981',
      title: 'User Interviews',
      description: 'Simulate in-depth discovery interviews with grounded personas to reveal daily workflows and unarticulated pain points.',
    },
    {
      type: 'landing_page_test',
      icon: <Compass size={19} />,
      iconBg: 'rgba(246, 200, 120, 0.12)',
      iconColor: '#F6C878',
      title: 'Concept & Demand',
      description: 'Validate product-market fit, value proposition desirability, and core feature hypotheses before writing code.',
    },
    {
      type: 'message_testing',
      icon: <MessageSquare size={19} />,
      iconBg: 'rgba(59, 130, 246, 0.12)',
      iconColor: '#3B82F6',
      title: 'Message Testing',
      description: 'Test pitch clarity, value proposition framing, and objection handling across customer demographic segments.',
    },
    {
      type: 'ab_test',
      icon: <BadgePercent size={19} />,
      iconBg: 'rgba(236, 72, 153, 0.12)',
      iconColor: '#EC4899',
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
            fontWeight: 500,
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

      {/* Wide Query Input Card */}
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: '1040px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: isFocused
            ? '1px solid rgba(246, 200, 120, 0.45)'
            : '1px solid rgba(255, 255, 255, 0.09)',
          borderRadius: '20px',
          padding: '20px 24px',
          position: 'relative',
          boxShadow: isFocused
            ? '0 16px 40px -10px rgba(0, 0, 0, 0.6), 0 0 20px rgba(246, 200, 120, 0.12)'
            : '0 12px 36px -10px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(16px)',
          marginBottom: '28px',
          transition: 'all 0.2s ease',
        }}
      >
        <textarea
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Describe your business idea, target audience, or pricing hypothesis (e.g., An AI study planner for students with a 250 BDT/month tier)..."
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
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
            paddingRight: '56px',
          }}
        />

        {/* Submit Arrow Button */}
        <button
          type="submit"
          aria-label="Start research study"
          style={{
            position: 'absolute',
            bottom: '18px',
            right: '20px',
            width: '38px',
            height: '38px',
            borderRadius: '50%',
            background: prompt.trim()
              ? 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)'
              : 'rgba(255, 255, 255, 0.08)',
            border: 'none',
            color: prompt.trim() ? '#080909' : '#6B7280',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: prompt.trim() ? 'pointer' : 'default',
            transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
            boxShadow: prompt.trim() ? '0 4px 14px rgba(246, 200, 120, 0.35)' : 'none',
          }}
        >
          <ArrowUp size={19} strokeWidth={2.5} />
        </button>
      </form>

      {/* 4 Study Type Quick Select Cards in One Single Line */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
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
              onClick={() => {
                setSelectedType(item.type);
                onStartStudy(item.type, prompt.trim() || undefined);
              }}
              style={{
                background: isSelected
                  ? 'rgba(246, 200, 120, 0.04)'
                  : 'rgba(255, 255, 255, 0.015)',
                border: isSelected
                  ? '1px solid rgba(246, 200, 120, 0.35)'
                  : '1px solid rgba(255, 255, 255, 0.07)',
                borderRadius: '16px',
                padding: '20px 18px',
                cursor: 'pointer',
                transition: 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
                position: 'relative',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'rgba(246, 200, 120, 0.35)';
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = isSelected
                  ? 'rgba(246, 200, 120, 0.35)'
                  : 'rgba(255, 255, 255, 0.07)';
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.background = isSelected
                  ? 'rgba(246, 200, 120, 0.04)'
                  : 'rgba(255, 255, 255, 0.015)';
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

