import React, { useState } from 'react';
import { Check, Sparkles, Zap, Shield, ArrowRight, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface PricingProps {
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const Pricing: React.FC<PricingProps> = ({ onOpenAuth }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSelectPlan = async (planId: 'free' | 'pro' | 'enterprise') => {
    setErrorMessage(null);

    if (planId === 'free') {
      if (isAuthenticated) {
        navigate('/app');
      } else if (onOpenAuth) {
        onOpenAuth('signup-options');
      } else {
        navigate('/auth/signup');
      }
      return;
    }

    if (!isAuthenticated) {
      if (onOpenAuth) {
        onOpenAuth('signin');
      } else {
        navigate('/auth/signin');
      }
      return;
    }

    try {
      setLoadingPlan(planId);
      const res = await api.createCheckoutSession(planId);
      if (res && res.url) {
        window.location.href = res.url;
      } else {
        throw new Error('No checkout URL received from payment provider');
      }
    } catch (err: any) {
      console.error('Checkout creation error:', err);
      setErrorMessage(err.message || 'Unable to initiate checkout. Please try again.');
    } finally {
      setLoadingPlan(null);
    }
  };

  const tiers = [
    {
      id: 'free' as const,
      name: 'Free Starter',
      price: '$0',
      period: 'forever',
      description: 'Ideal for indie hackers & student founders testing synthetic interview feasibility.',
      badge: null,
      popular: false,
      icon: Zap,
      features: [
        '3 active customer research studies',
        '5 synthetic personas per study',
        'Aggregated free LLM provider pool (200+ routes)',
        'Standard interactive interview simulator',
        'Basic demographic & persona attribute cards',
        'Community Discord & docs support',
      ],
      ctaText: isAuthenticated ? 'Go to Dashboard' : 'Get Started Free',
    },
    {
      id: 'pro' as const,
      name: 'Pro Researcher',
      price: '$29',
      period: 'per month',
      description: 'For founders, PMs, and UX researchers validating real market willingness to pay.',
      badge: 'MOST POPULAR',
      popular: true,
      icon: Sparkles,
      features: [
        'Unlimited active research studies',
        '50 grounded synthetic personas per study',
        'Empirical evidence grounding (HuggingFace datasets)',
        'Verified citations with paper & source URLs',
        'Priority high-capacity reasoning model routes',
        'Multi-segment behavioral simulations',
        'Complete PDF & JSON audit export reports',
      ],
      ctaText: 'Upgrade to Pro',
    },
    {
      id: 'enterprise' as const,
      name: 'Team & Scale',
      price: '$99',
      period: 'per month',
      description: 'For agencies, accelerators, and venture studios running continuous customer discovery.',
      badge: 'UNLIMITED POWER',
      popular: false,
      icon: Shield,
      features: [
        'Everything in Pro Researcher',
        'Dedicated LLM routing capacity & failover SLAs',
        'Unlimited personas & batch parallel interviews',
        'Custom proprietary dataset ingestion',
        'Custom Big Five & demographic archetypes',
        'Workspace collaboration & multi-seat sharing',
        'Direct priority engineering support',
      ],
      ctaText: 'Subscribe to Enterprise',
    },
  ];

  return (
    <section
      id="pricing"
      style={{
        position: 'relative',
        padding: '110px 0',
        zIndex: 1,
        background: '#080909',
      }}
    >
      <div
        style={{
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {/* Section Header */}
        <div style={{ textAlign: 'center', maxWidth: '760px', margin: '0 auto 64px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 16px',
              background: 'rgba(246, 200, 120, 0.06)',
              border: '1px solid rgba(246, 200, 120, 0.2)',
              borderRadius: '999px',
              fontSize: '0.8rem',
              fontWeight: 600,
              color: '#F6C878',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: '20px',
            }}
          >
            <Sparkles size={14} />
            <span>Transparent Pricing</span>
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.5vw, 2.75rem)',
              fontWeight: 700,
              letterSpacing: '-0.03em',
              color: '#F3F4F6',
              lineHeight: 1.15,
              marginBottom: '16px',
            }}
          >
            Scale Synthetic Customer Research with Confidence
          </h2>

          <p
            style={{
              fontSize: '1.05rem',
              color: '#9CA3AF',
              lineHeight: 1.6,
            }}
          >
            Zero hallucinated personas. Transparent pricing backed by secure Stripe checkout. Cancel anytime.
          </p>

          {errorMessage && (
            <div
              style={{
                marginTop: '20px',
                padding: '12px 18px',
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: '8px',
                color: '#FCA5A5',
                fontSize: '0.9rem',
              }}
            >
              {errorMessage}
            </div>
          )}
        </div>

        {/* Pricing Cards Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '28px',
            alignItems: 'stretch',
          }}
        >
          {tiers.map((tier) => {
            const Icon = tier.icon;
            const isSelectedLoading = loadingPlan === tier.id;

            return (
              <div
                key={tier.id}
                style={{
                  position: 'relative',
                  display: 'flex',
                  flexDirection: 'column',
                  background: tier.popular
                    ? 'linear-gradient(180deg, rgba(30, 26, 18, 0.85) 0%, rgba(17, 18, 20, 0.95) 100%)'
                    : '#111214',
                  border: tier.popular
                    ? '1.5px solid rgba(246, 200, 120, 0.45)'
                    : '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '16px',
                  padding: '36px 32px',
                  boxShadow: tier.popular
                    ? '0 20px 50px -15px rgba(246, 200, 120, 0.15), 0 0 25px rgba(246, 200, 120, 0.05)'
                    : '0 12px 30px -10px rgba(0, 0, 0, 0.5)',
                  transition: 'transform 0.25s ease, border-color 0.25s ease',
                }}
              >
                {/* Popular Badge */}
                {tier.badge && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '-13px',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      padding: '4px 14px',
                      background: 'linear-gradient(90deg, #F6C878 0%, #D49A3D 100%)',
                      color: '#080909',
                      borderRadius: '999px',
                      fontSize: '0.72rem',
                      fontWeight: 800,
                      letterSpacing: '0.08em',
                      boxShadow: '0 4px 14px rgba(246, 200, 120, 0.3)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {tier.badge}
                  </div>
                )}

                {/* Tier Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
                  <div
                    style={{
                      width: '40px',
                      height: '40px',
                      borderRadius: '10px',
                      background: tier.popular ? 'rgba(246, 200, 120, 0.12)' : 'rgba(255, 255, 255, 0.05)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: tier.popular ? '#F6C878' : '#D1D5DB',
                    }}
                  >
                    <Icon size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#F3F4F6', margin: 0 }}>
                      {tier.name}
                    </h3>
                  </div>
                </div>

                <p
                  style={{
                    fontSize: '0.88rem',
                    color: '#9CA3AF',
                    lineHeight: 1.5,
                    minHeight: '42px',
                    marginBottom: '24px',
                  }}
                >
                  {tier.description}
                </p>

                {/* Price Display */}
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '28px' }}>
                  <span
                    style={{
                      fontSize: '2.75rem',
                      fontWeight: 800,
                      color: '#FFFFFF',
                      letterSpacing: '-0.03em',
                    }}
                  >
                    {tier.price}
                  </span>
                  <span style={{ fontSize: '0.9rem', color: '#9CA3AF', fontWeight: 500 }}>
                    /{tier.period}
                  </span>
                </div>

                {/* CTA Button */}
                <button
                  type="button"
                  onClick={() => handleSelectPlan(tier.id)}
                  disabled={isSelectedLoading}
                  style={{
                    width: '100%',
                    padding: '14px 20px',
                    borderRadius: '10px',
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    cursor: isSelectedLoading ? 'not-allowed' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    border: 'none',
                    background: tier.popular
                      ? 'linear-gradient(90deg, #F6C878 0%, #E6AF56 100%)'
                      : 'rgba(255, 255, 255, 0.08)',
                    color: tier.popular ? '#080909' : '#FFFFFF',
                    boxShadow: tier.popular ? '0 6px 20px rgba(246, 200, 120, 0.25)' : 'none',
                    transition: 'all 0.2s ease',
                    marginBottom: '32px',
                  }}
                >
                  {isSelectedLoading ? (
                    <>
                      <Loader2 size={18} className="animate-spin" />
                      <span>Connecting to Stripe...</span>
                    </>
                  ) : (
                    <>
                      <span>{tier.ctaText}</span>
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>

                {/* Feature List */}
                <div style={{ flexGrow: 1 }}>
                  <div
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: '#9CA3AF',
                      letterSpacing: '0.05em',
                      textTransform: 'uppercase',
                      marginBottom: '16px',
                    }}
                  >
                    What's included
                  </div>
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {tier.features.map((feature, idx) => (
                      <li
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          fontSize: '0.88rem',
                          color: '#D1D5DB',
                          lineHeight: 1.45,
                        }}
                      >
                        <div
                          style={{
                            marginTop: '2px',
                            color: tier.popular ? '#F6C878' : '#10B981',
                            flexShrink: 0,
                          }}
                        >
                          <Check size={16} />
                        </div>
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>

        {/* Stripe Trust Footer */}
        <div
          style={{
            marginTop: '56px',
            textAlign: 'center',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            color: '#6B7280',
            fontSize: '0.84rem',
          }}
        >
          <Shield size={16} color="#9CA3AF" />
          <span>Payments securely processed by Stripe. All major credit cards accepted with 256-bit encryption.</span>
        </div>
      </div>
    </section>
  );
};
