import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { StudioPricing } from './StudioPricing';

interface PricingProps {
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const Pricing: React.FC<PricingProps> = ({ onOpenAuth }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [paymentsUnavailable, setPaymentsUnavailable] = useState(false);
  const [billingEnabled, setBillingEnabled] = useState(false);
  useEffect(() => {
    let current = true;
    setBillingEnabled(false);
    if (isAuthenticated && !api.isMockMode()) {
      void api.getSubscription().then((subscription) => {
        if (current) setBillingEnabled(subscription.billing_enabled === true);
      }).catch(() => { if (current) setBillingEnabled(false); });
    }
    return () => { current = false; };
  }, [isAuthenticated]);

  /** Only the backend can tell us checkout is switched off in this build —
   * every other failure (network, 429, decline) stays undiagnosed. */
  const isPaymentsNotConfigured = (err: unknown): boolean => {
    const detail = `${(err as { message?: string })?.message || ''}`.toLowerCase();
    return (
      detail.includes('not configured') ||
      detail.includes('not enabled') ||
      detail.includes('stripe secret key') ||
      detail.includes('payments are disabled')
    );
  };

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

    if (!billingEnabled || loadingPlan) return;
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
    } catch (err: unknown) {
      // The backend detail can name unconfigured infrastructure ("Stripe secret
      // key is not configured") — keep it for developers, never show it to visitors.
      if (isPaymentsNotConfigured(err)) {
        setBillingEnabled(false);
        setPaymentsUnavailable(true);
        setErrorMessage(
          "Paid plans are not enabled. No payment was taken and no paid access was granted."
        );
      } else {
        setErrorMessage("We couldn't start checkout. Please try again.");
      }
    } finally {
      setLoadingPlan(null);
    }
  };

  const tiers = [
    {
      id: 'free' as const,
      name: 'Free Starter',
      price: '$0',
      period: 'no card required',
      description: 'For early questions, interview practice, and exploratory product research.',
      features: [
        'Studies within the server admission limits',
        'Personas selected locally from public synthetic sources',
        'Interviews on remote models, subject to availability',
        'Editable scripts and multi-turn interviews',
        'Saved transcripts and decision reports',
        'Evidence, inference, and synthetic claims kept distinct',
      ],
      ctaText: 'Open workspace',
    },
    {
      id: 'pro' as const,
      name: 'Pro Researcher',
      price: '$29',
      period: 'per month',
      description: 'Paid access only where enabled and verified by the server.',
      features: [
        'Server-defined study and persona limits',
        'Evidence retrieval over public research datasets',
        'Evidence panel: inspect the records behind evidence-backed attributes',
        'The same governed, quality-preserving routing policy',
        'Multi-segment behavioral simulations',
        'Decision reports with the provenance trail behind every finding',
      ],
      ctaText: 'Upgrade to Pro',
    },
    {
      id: 'enterprise' as const,
      name: 'Team & Scale',
      price: '$99',
      period: 'per month',
      description: 'For agencies, accelerators, and venture studios running continuous customer discovery.',
      features: [
        'Everything in Pro Researcher',
        'Server-defined admission and research limits',
        'Synthetic interview and report workflows',
        'No automatic collaboration or provider-priority entitlement',
      ],
      ctaText: 'Subscribe to Enterprise',
    },
  ];

  return <StudioPricing tiers={tiers} billingEnabled={billingEnabled} loadingPlan={loadingPlan}
    errorMessage={errorMessage} paymentsUnavailable={paymentsUnavailable} onSelectPlan={handleSelectPlan} />;
};
