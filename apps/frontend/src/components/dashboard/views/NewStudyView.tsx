import React, { useState } from 'react';
import {
  Users,
  Layout,
  MessageSquare,
  GitCompare,
  ArrowUp,
  Sparkles,
} from 'lucide-react';
import { StudyType } from '../../../types';

interface NewStudyViewProps {
  onStartStudy: (type: StudyType, initialPrompt?: string) => void;
}

export const NewStudyView: React.FC<NewStudyViewProps> = ({ onStartStudy }) => {
  const [prompt, setPrompt] = useState('');
  const [selectedType, setSelectedType] = useState<StudyType>('interviews');

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
      icon: <Users size={20} />,
      iconBg: 'rgba(16, 185, 129, 0.12)',
      iconColor: '#10B981',
      title: 'User Interviews',
      description: 'Interview your exact audience, from first idea to live funnel.',
    },
    {
      type: 'landing_page_test',
      icon: <Layout size={20} />,
      iconBg: 'rgba(246, 200, 120, 0.12)',
      iconColor: '#F6C878',
      title: 'Landing Page Test',
      description: 'See how your page scores with your target audience, on the intent you pick.',
    },
    {
      type: 'message_testing',
      icon: <MessageSquare size={20} />,
      iconBg: 'rgba(59, 130, 246, 0.12)',
      iconColor: '#3B82F6',
      title: 'Message Testing',
      description: 'Test which words land with your audience before they ship.',
    },
    {
      type: 'ab_test',
      icon: <GitCompare size={20} />,
      iconBg: 'rgba(236, 72, 153, 0.12)',
      iconColor: '#EC4899',
      title: 'A/B Test',
      description: 'Show two different landing pages to your target audience and see which one wins, and why.',
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
        padding: '40px 24px',
        maxWidth: '960px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* Title & Subtitle */}
      <div style={{ textAlign: 'center', marginBottom: '36px' }}>
        <h1
          style={{
            fontSize: 'clamp(2rem, 3.5vw, 2.75rem)',
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
            fontSize: '1rem',
            color: '#9CA3AF',
            margin: 0,
            letterSpacing: '-0.01em',
          }}
        >
          Ask anything, or pick any study type from below.
        </p>
      </div>

      {/* Big Query Input Card */}
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%',
          maxWidth: '740px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid rgba(255, 255, 255, 0.09)',
          borderRadius: '20px',
          padding: '16px 20px',
          position: 'relative',
          boxShadow: '0 12px 36px -10px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(16px)',
          marginBottom: '36px',
          transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
        }}
      >
        <textarea
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Should we lead with pricing or with the product story?"
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
            lineHeight: 1.5,
            resize: 'none',
            fontFamily: 'inherit',
            paddingRight: '48px',
          }}
        />

        {/* Submit Arrow Button */}
        <button
          type="submit"
          aria-label="Start research study"
          style={{
            position: 'absolute',
            bottom: '16px',
            right: '16px',
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: prompt.trim()
              ? 'linear-gradient(135deg, #F6C878 0%, #D4AF37 100%)'
              : 'rgba(255, 255, 255, 0.08)',
            border: 'none',
            color: prompt.trim() ? '#080909' : '#6B7280',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
            boxShadow: prompt.trim() ? '0 4px 12px rgba(246, 200, 120, 0.3)' : 'none',
          }}
        >
          <ArrowUp size={18} strokeWidth={2.5} />
        </button>
      </form>

      {/* 4 Study Type Quick Select Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
          width: '100%',
          maxWidth: '740px',
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
                  width: '38px',
                  height: '38px',
                  borderRadius: '10px',
                  background: item.iconBg,
                  color: item.iconColor,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {item.icon}
              </div>

              {/* Text */}
              <div>
                <h2
                  style={{
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    color: '#FFFFFF',
                    margin: '0 0 4px 0',
                    letterSpacing: '-0.01em',
                  }}
                >
                  {item.title}
                </h2>
                <p
                  style={{
                    fontSize: '0.8rem',
                    color: '#8A909A',
                    margin: 0,
                    lineHeight: 1.4,
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
