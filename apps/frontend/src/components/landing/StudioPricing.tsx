import React from 'react';
import { ArrowRight, Check } from 'lucide-react';

interface PricingTier {
  id: 'free' | 'pro' | 'enterprise';
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  ctaText: string;
}

interface StudioPricingProps {
  tiers: PricingTier[];
  billingEnabled: boolean;
  loadingPlan: string | null;
  errorMessage: string | null;
  paymentsUnavailable: boolean;
  onSelectPlan: (planId: PricingTier['id']) => Promise<void>;
}

export const StudioPricing: React.FC<StudioPricingProps> = ({
  tiers, billingEnabled, loadingPlan, errorMessage, paymentsUnavailable, onSelectPlan,
}) => (
  <section id="pricing" className="studio-section studio-pricing" aria-labelledby="studio-pricing-title" tabIndex={-1}>
    <div className="studio-container">
      <div className="studio-section-heading">
        <h2 id="studio-pricing-title">Start without a card.</h2>
        <p>The first plan costs nothing. Interviews run on remote models, so availability and quotas apply.</p>
      </div>
      {errorMessage && <p className="studio-error" role="alert">{errorMessage}</p>}
      <div className="studio-plans">
        {tiers.filter((tier) => tier.id === 'free' || billingEnabled).map((tier) => (
          <article key={tier.id} className="studio-plan" aria-labelledby={`studio-plan-${tier.id}`}>
            <div className="studio-plan-summary">
              <h3 id={`studio-plan-${tier.id}`}>{tier.name}</h3>
              <p className="studio-plan-price"><strong>{tier.price}</strong><span>{tier.period}</span></p>
              <p>{tier.description}</p>
              <button type="button" className="studio-button" onClick={() => void onSelectPlan(tier.id)}
                disabled={loadingPlan !== null} aria-busy={loadingPlan === tier.id}>
                {loadingPlan === tier.id ? 'Opening checkout...' : tier.ctaText}
                <ArrowRight size={17} aria-hidden="true" />
              </button>
            </div>
            <ul>
              {tier.features.map((feature) => (
                <li key={feature}><Check size={17} aria-hidden="true" /><span>{feature}</span></li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <p className="studio-billing-note">
        {paymentsUnavailable
          ? 'Paid plans are not enabled in this build. No payment is taken.'
          : billingEnabled
            ? 'Paid plans are processed by Stripe. Access changes only after server confirmation.'
            : 'Paid plans are not available yet.'}
      </p>
    </div>
  </section>
);