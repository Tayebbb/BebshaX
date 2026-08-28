/**
 * TypeScript types for Stripe payments and subscription tiers.
 */

export type SubscriptionPlan = 'free' | 'pro' | 'enterprise';

export interface SubscriptionStatus {
  plan: SubscriptionPlan | string;
  status: 'active' | 'canceled' | 'past_due' | 'unpaid' | string;
  is_paid: boolean;
  expires_at?: string | null;
  has_billing_account: boolean;
}

export interface CheckoutSessionResponse {
  session_id: string;
  url: string;
  plan: string;
}

export interface PortalSessionResponse {
  url: string;
}

export interface PricingTier {
  id: SubscriptionPlan;
  name: string;
  price: string;
  period: string;
  description: string;
  badge?: string;
  features: string[];
  cta: string;
  popular?: boolean;
}
