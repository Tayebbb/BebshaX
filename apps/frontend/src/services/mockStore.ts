/**
 * Mock-mode state store and canned-content builders.
 *
 * Extracted from services/api.ts so test scaffolding no longer lives inside
 * the production client module. Everything here is only reachable when
 * api.isMockMode() is true (vitest, VITE_MOCK=1) — live mode throws instead
 * of serving canned content. Zero behavior change from the inlined originals.
 */
import {
  Business,
  Conversation,
  DemoLabRunResult,
  DemoLabScenariosResponse,
  EvidenceClaim,
  EvidenceSource,
  MemoryItem,
  Persona,
  PersonaRoleSuggestion,
  ProvenanceRecord,
  ResearchRun,
  Study,
  StudyType,
} from '../types';
import { DatasetSource } from '../types/dataset';
import {
  mockBusinesses,
  mockConversations,
  mockDatasets,
  mockEvidenceClaims,
  mockEvidenceSources,
  mockMemories,
  mockPersonas,
  mockProvenanceRecords,
  mockStudies,
} from '../mocks/fixtures';

// Re-exported so api.ts has a single lazy entry point into the mock layer —
// it must never import ../mocks/fixtures statically (prod-bundle eviction).
export { mockEvaluationMetrics, mockHealth, mockRoutesStatus } from '../mocks/fixtures';

/** Judge Lab fixture (mock mode only) — a small, clearly-simulated scenario set. */
export const mockDemoLabScenarios: DemoLabScenariosResponse = {
  enabled: true,
  simulated: true,
  scenarios: [
    {
      name: 'provider_429_fallback',
      title: 'Provider rate-limits (429) → fallback',
      description: 'First route answers 429; the router classifies RATE_LIMITED, cools it down and serves from the next candidate.',
      expected_outcome: 'served_after_fallback',
    },
    {
      name: 'all_providers_down',
      title: 'Every provider down → explicit failure',
      description: 'All candidates fail; nothing is fabricated and the API returns all_candidates_failed (503).',
      expected_outcome: 'explicit_failure',
    },
  ],
};

export function mockDemoLabRun(name: string): DemoLabRunResult {
  if (name === 'all_providers_down') {
    return {
      scenario: name,
      title: 'Every provider down → explicit failure',
      simulated: true,
      outcome: 'explicit_failure',
      error_code: 'all_candidates_failed',
      explanation: 'Both scripted routes failed with SERVER_ERROR. The router exhausted its candidates and raised an explicit failure instead of inventing a reply.',
      provenance: null,
      timeline: [
        { step: 'REQUEST', provider: null, model: null, result: 'served', failure_kind: null, fallback_reason: null, latency_ms: 0 },
        { step: 'FAILURE', provider: 'alpha', model: 'alpha-8b', result: 'failed', failure_kind: 'SERVER_ERROR', fallback_reason: 'HTTP 503 from provider', latency_ms: 42 },
        { step: 'FAILURE', provider: 'beta', model: 'beta-7b', result: 'failed', failure_kind: 'SERVER_ERROR', fallback_reason: 'HTTP 502 from provider', latency_ms: 38 },
        { step: 'EXPLICIT FAILURE', provider: null, model: null, result: 'failed', failure_kind: null, fallback_reason: 'all_candidates_failed', latency_ms: null },
      ],
      extra: { attempts: 2 },
    };
  }
  return {
    scenario: name,
    title: 'Provider rate-limits (429) → fallback',
    simulated: true,
    outcome: 'served_after_fallback',
    error_code: null,
    explanation: 'The first scripted route returned HTTP 429. The router classified it RATE_LIMITED, put the route on cooldown and served the request from the next candidate.',
    provenance: null,
    timeline: [
      { step: 'REQUEST', provider: null, model: null, result: 'served', failure_kind: null, fallback_reason: null, latency_ms: 0 },
      { step: 'FAILURE', provider: 'alpha', model: 'alpha-8b', result: 'failed', failure_kind: 'RATE_LIMITED', fallback_reason: 'HTTP 429 from provider', latency_ms: 51 },
      { step: 'FALLBACK', provider: 'beta', model: 'beta-7b', result: 'skipped', failure_kind: null, fallback_reason: 'route on cooldown', latency_ms: null },
      { step: 'SUCCESS', provider: 'gamma', model: 'gamma-9b', result: 'served', failure_kind: null, fallback_reason: null, latency_ms: 120 },
    ],
    extra: { cooldown_seconds: 60 },
  };
}

// In-memory state store for client modifications during mock/fallback mode
export class MockStore {
  businesses: Business[] = [];
  personas: Record<string, Persona> = {};
  memories: Record<string, MemoryItem[]> = {};
  conversations: Record<string, Conversation> = {};
  provenance: ProvenanceRecord[] = [];
  studies: Study[] = [];
  datasets: DatasetSource[] = [];
  sources: EvidenceSource[] = [];
  claims: EvidenceClaim[] = [];
  researchRuns: ResearchRun[] = [];

  constructor() {
    this.reset();
  }

  reset() {
    this.businesses = JSON.parse(JSON.stringify(mockBusinesses));
    this.personas = JSON.parse(JSON.stringify(mockPersonas));
    this.memories = JSON.parse(JSON.stringify(mockMemories));
    this.conversations = JSON.parse(JSON.stringify(mockConversations));
    this.provenance = JSON.parse(JSON.stringify(mockProvenanceRecords));
    this.studies = JSON.parse(JSON.stringify(mockStudies));
    this.datasets = JSON.parse(JSON.stringify(mockDatasets));
    this.sources = JSON.parse(JSON.stringify(mockEvidenceSources));
    this.claims = JSON.parse(JSON.stringify(mockEvidenceClaims));
    this.researchRuns = [];
  }
}

export const mockStore = new MockStore();

export interface MockCopilotReply {
  reply: string;
  suggested_study_type: StudyType;
  is_ready_for_approval: boolean;
  research_goal_card?: {
    title: string;
    summary: string;
    target_audience: string;
    core_hypothesis: string;
  } | null;
  suggested_roles?: PersonaRoleSuggestion[];
  served_by: string;
}

/** Canned local copilot engine used by sendStudyCopilotMessage in mock mode.
 * Its route label is distinct from the backend's `bebshax/copilot-engine`
 * (the live keyword-template fallback) so the UI's template warning only
 * fires for a real degraded backend; mock mode is labelled globally as sample data. */
const MOCK_COPILOT_ROUTE = 'mock/sample-copilot';

export function mockCopilotReply(
  messages: { role: 'user' | 'assistant'; content: string }[]
): MockCopilotReply {
  const userTurns = messages.filter((m) => m.role === 'user');
  const turnCount = userTurns.length;
  const firstText = userTurns[0]?.content || '';
  const lastText = userTurns[userTurns.length - 1]?.content || '';
  const combinedText = (firstText + ' ' + lastText).toLowerCase();

  const hasPricing = /price|cost|month|subscription|plan|\$|taka|bdt|€|£|free/.test(combinedText);
  const hasStudents = /student|school|college|university|study planner|academic|exam/.test(combinedText);
  const hasPriceTracker = /price tracker|price-tracker|tracker|price track|deal alert|price drop|deal hunter/.test(combinedText);
  const hasFood = /food|restaurant|delivery|meal|eat|chef|recipe|cuisine/.test(combinedText);
  const hasHealth = /health|fitness|gym|workout|diet|wellness|doctor|medical/.test(combinedText);
  const hasFintech = /payment|bank|finance|loan|invest|money|wallet|crypto/.test(combinedText);
  const hasEcommerce = /shop|sell|buy|store|marketplace|fashion/.test(combinedText);
  const hasB2B = /saas|enterprise|team|office|workflow|productivity|b2b|business tool/.test(combinedText);

  let productType = 'product or service';
  let audienceQ = 'Who is your primary target user — what\'s their age range, lifestyle, or professional context? And what geography are you launching in first?';
  let followupQ = 'What\'s the core problem you\'re solving for them, and what\'s the price point or business model you\'re validating?';
  let roles: PersonaRoleSuggestion[] = [];

  if (hasStudents) {
    productType = 'education or student-focused product';
    audienceQ = 'What level of students — K-12, university, or professional learners? And what geography?';
    followupQ = 'Is this B2C for students directly, or B2B (schools/universities)? And what\'s the price point?';
    roles = [
      { id: 'role_uni_student', role: 'UNIVERSITY STUDENT', description: 'Core target user — validates product-market fit and willingness to pay.', count: 3, selected: true },
      { id: 'role_college_applicant', role: 'COLLEGE APPLICANT', description: 'High-stakes test-taker — validates premium tier and urgency.', count: 3, selected: true },
      { id: 'role_high_schooler', role: 'BUSY HIGH SCHOOLER', description: 'Time-pressed student — tests core value delivery.', count: 3, selected: true },
      { id: 'role_parental_buyer', role: 'PARENTAL BUYER', description: 'Parent paying for child\'s tools — validates pricing framing and trust.', count: 0, selected: false },
      { id: 'role_budget_student', role: 'BUDGET-CONSCIOUS STUDENT', description: 'Price-sensitive student — tests pricing floor and free tier.', count: 0, selected: false },
    ];
  } else if (hasPriceTracker) {
    productType = 'price tracker & deal intelligence website';
    audienceQ = 'Who are your primary users — online deal hunters, budget planners, or frequent gadget/apparel shoppers? And what retail platforms will you track first?';
    followupQ = 'What specific alert channels (SMS, email, push) and historical price analytics will prove the 100 taka/month value proposition?';
    roles = [
      { id: 'role_bargain_hunter', role: 'SMART BARGAIN HUNTER', description: 'Active online shopper monitoring sales and deals — tests willingness to pay 100 taka/month for instant alerts.', count: 3, selected: true },
      { id: 'role_tech_shopper', role: 'TECH-SAVVY CONSUMER', description: 'Frequent e-commerce buyer tracking price drops across multiple marketplaces.', count: 3, selected: true },
      { id: 'role_budget_planner', role: 'BUDGET-CONSCIOUS BUYER', description: 'Price-sensitive household planner validating monthly subscription ROI.', count: 3, selected: true },
      { id: 'role_deal_skeptic', role: 'DEAL SKEPTIC', description: 'Consumer comparing free price trackers vs paid premium alert features.', count: 0, selected: false },
      { id: 'role_impulse_shopper', role: 'IMPULSE BUYER', description: 'Occasional shopper testing if historical price charts influence purchase timing.', count: 0, selected: false },
    ];
  } else if (hasFood) {
    productType = 'food or restaurant service';
    audienceQ = 'Who are the primary customers — home cooks, busy professionals, or families? And what region or city are you targeting first?';
    followupQ = 'What\'s the main value proposition — convenience, cost savings, or quality? And what price point are you considering?';
    roles = [
      { id: 'role_busy_professional', role: 'BUSY PROFESSIONAL', description: 'Time-pressed professional who values convenience over price — core paying customer.', count: 3, selected: true },
      { id: 'role_home_cook', role: 'HOME COOK', description: 'Cooking enthusiast who compares against cooking at home — key value benchmark.', count: 3, selected: true },
      { id: 'role_family_planner', role: 'FAMILY MEAL PLANNER', description: 'Parent managing family nutrition and budget — represents group/family subscription potential.', count: 3, selected: true },
      { id: 'role_health_conscious', role: 'HEALTH-CONSCIOUS EATER', description: 'Health-focused user with dietary needs — tests premium tier demands.', count: 0, selected: false },
      { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Value-maximizer who compares cost per meal — tests pricing floor.', count: 0, selected: false },
    ];
  } else if (hasHealth) {
    productType = 'health & wellness product';
    audienceQ = 'Who is your primary user — fitness enthusiasts, people with health conditions, or a broader wellness audience?';
    followupQ = 'Is this B2C or B2B (gyms, clinics)? And what\'s the rough price point?';
    roles = [
      { id: 'role_fitness_enthusiast', role: 'FITNESS ENTHUSIAST', description: 'Regular gym-goer — primary power user who validates core features.', count: 3, selected: true },
      { id: 'role_wellness_beginner', role: 'WELLNESS BEGINNER', description: 'Person starting their health journey — tests onboarding and motivational hooks.', count: 3, selected: true },
      { id: 'role_chronic_user', role: 'CHRONIC CONDITION USER', description: 'Person managing a health condition — tests specialized depth and accuracy.', count: 3, selected: true },
      { id: 'role_time_poor', role: 'TIME-POOR PROFESSIONAL', description: 'High-income, low-time user — validates premium tier.', count: 0, selected: false },
      { id: 'role_skeptic', role: 'HEALTH APP SKEPTIC', description: 'Person who tried and failed at health apps — reveals key churn drivers.', count: 0, selected: false },
    ];
  } else if (hasFintech) {
    productType = 'fintech product';
    audienceQ = 'Who is your primary user — individuals, small businesses, or enterprises? And what geography are you targeting?';
    followupQ = 'What financial problem are you solving — payments, savings, credit, or investments?';
    roles = [
      { id: 'role_early_adopter', role: 'EARLY ADOPTER PRO', description: 'Tech-savvy individual comfortable with financial apps — validates core assumptions.', count: 3, selected: true },
      { id: 'role_small_biz', role: 'SMALL BUSINESS OWNER', description: 'SMB operator managing cash flow — high-value B2B2C segment.', count: 3, selected: true },
      { id: 'role_underbanked', role: 'UNDERBANKED USER', description: 'Person with limited banking access — tests financial inclusion positioning.', count: 3, selected: true },
      { id: 'role_security_skeptic', role: 'SECURITY SKEPTIC', description: 'Privacy-first user — reveals trust barriers.', count: 0, selected: false },
      { id: 'role_high_net', role: 'HIGH NET WORTH USER', description: 'Affluent user with complex needs — tests premium ceiling.', count: 0, selected: false },
    ];
  } else if (hasEcommerce) {
    productType = 'e-commerce or marketplace';
    audienceQ = 'Who are your primary buyers — consumers or businesses? And what product category are you focused on?';
    followupQ = 'Are you a marketplace or direct retailer? And what\'s the target geography and price range?';
    roles = [
      { id: 'role_impulse_buyer', role: 'IMPULSE BUYER', description: 'Discovery-driven shopper — tests conversion and merchandising.', count: 3, selected: true },
      { id: 'role_research_first', role: 'RESEARCH-FIRST BUYER', description: 'Methodical shopper — tests trust signals and pricing clarity.', count: 3, selected: true },
      { id: 'role_loyal_repeater', role: 'LOYAL REPEATER', description: 'Returning customer — tests retention and loyalty programs.', count: 3, selected: true },
      { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Discount-motivated buyer — tests pricing floor.', count: 0, selected: false },
      { id: 'role_premium_seeker', role: 'PREMIUM SEEKER', description: 'Quality-over-price buyer — tests premium positioning.', count: 0, selected: false },
    ];
  } else if (hasB2B) {
    productType = 'B2B SaaS or business tool';
    audienceQ = 'What size companies are you targeting — SMBs, mid-market, or enterprise? And what industry does this serve?';
    followupQ = 'What is the primary workflow or problem being solved? And what\'s your pricing model?';
    roles = [
      { id: 'role_decision_maker', role: 'BUDGET DECISION MAKER', description: 'Manager who approves tool purchases — validates ROI narrative.', count: 3, selected: true },
      { id: 'role_power_user', role: 'DAILY POWER USER', description: 'Individual contributor using the tool most — validates UX depth.', count: 3, selected: true },
      { id: 'role_it_eval', role: 'IT SECURITY EVALUATOR', description: 'Tech gatekeeping role — tests compliance and integration.', count: 3, selected: true },
      { id: 'role_champion', role: 'INTERNAL CHAMPION', description: 'Early adopter who advocates internally — tests viral mechanics.', count: 0, selected: false },
      { id: 'role_resistant', role: 'CHANGE-RESISTANT USER', description: 'Employee reluctant to adopt — reveals adoption barriers.', count: 0, selected: false },
    ];
  } else {
    roles = [
      { id: 'role_primary', role: 'PRIMARY USER', description: 'Core target user — validates product-market fit and core value proposition.', count: 3, selected: true },
      { id: 'role_early_adopter', role: 'EARLY ADOPTER', description: 'Tech-forward user open to new solutions — validates initial demand.', count: 3, selected: true },
      { id: 'role_price_conscious', role: 'PRICE-CONSCIOUS USER', description: 'Budget-sensitive potential customer — validates pricing model.', count: 3, selected: true },
      { id: 'role_skeptic', role: 'SKEPTICAL NON-USER', description: 'Person using a competitor — reveals switching barriers.', count: 0, selected: false },
      { id: 'role_power_user', role: 'POWER USER', description: 'Heavy user who needs advanced features — validates depth.', count: 0, selected: false },
    ];
  }

  if (turnCount === 1) {
    return {
      reply: `Got it — you're exploring an ${productType}${hasPricing ? ' with a target pricing model' : ''}. User Interviews are ideal here to uncover mental models, key objections, and real willingness to pay.\n\n${audienceQ}`,
      suggested_study_type: 'interviews',
      is_ready_for_approval: false,
      research_goal_card: null,
      suggested_roles: roles,
      served_by: MOCK_COPILOT_ROUTE,
    };
  } else if (turnCount === 2) {
    return {
      reply: followupQ,
      suggested_study_type: 'interviews',
      is_ready_for_approval: false,
      research_goal_card: null,
      suggested_roles: roles,
      served_by: MOCK_COPILOT_ROUTE,
    };
  } else {
    return {
      reply: "I've synthesized your inputs into a focused research goal proposal below:",
      suggested_study_type: 'interviews',
      is_ready_for_approval: true,
      research_goal_card: {
        title: 'RESEARCH GOAL',
        summary: `Validate whether your ${productType} solves a genuine need for target users and determine demand${hasPricing ? ' at your target price point' : ''}. Does this capture what you're looking for?`,
        target_audience: `Target users of the ${productType}`,
        core_hypothesis: `Demand and product-market fit for the ${productType}`,
      },
      suggested_roles: roles,
      served_by: MOCK_COPILOT_ROUTE,
    };
  }
}

/** Context-aware fallback roles derived from the study prompt (mock mode). */
export function mockSuggestedRoles(studyPrompt: string): PersonaRoleSuggestion[] {
  const promptLower = studyPrompt.toLowerCase();
  if (/tracker|track|price|deal|discount|compare|monitoring|shopping|ecommerce|taka/.test(promptLower)) {
    return [
      { id: 'role_bargain_hunter', role: 'SMART BARGAIN HUNTER', description: 'Active online shopper monitoring sales and deals — validates 100 taka/mo pricing.', count: 3, selected: true },
      { id: 'role_tech_shopper', role: 'TECH-SAVVY CONSUMER', description: 'Frequent buyer tracking price drops across marketplaces.', count: 3, selected: true },
      { id: 'role_budget_planner', role: 'BUDGET-CONSCIOUS BUYER', description: 'Price-sensitive household planner validating monthly subscription ROI.', count: 3, selected: true },
      { id: 'role_deal_skeptic', role: 'DEAL SKEPTIC', description: 'Consumer comparing free price trackers vs paid premium alert features.', count: 0, selected: false },
      { id: 'role_impulse_shopper', role: 'IMPULSE BUYER', description: 'Occasional shopper testing if historical price charts influence purchase timing.', count: 0, selected: false },
    ];
  } else if (/food|restaurant|delivery|meal|eat/.test(promptLower)) {
    return [
      { id: 'role_busy_professional', role: 'BUSY PROFESSIONAL', description: 'Time-pressed professional — core convenience-driven paying customer.', count: 3, selected: true },
      { id: 'role_home_cook', role: 'HOME COOK', description: 'Cooking enthusiast — key value-vs-cooking-at-home benchmark.', count: 3, selected: true },
      { id: 'role_family_planner', role: 'FAMILY MEAL PLANNER', description: 'Parent managing family nutrition — represents group/family segment.', count: 3, selected: true },
      { id: 'role_health_conscious', role: 'HEALTH-CONSCIOUS EATER', description: 'Dietary-needs user — tests premium tier.', count: 0, selected: false },
      { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Value-seeker — tests pricing floor.', count: 0, selected: false },
    ];
  } else if (/health|fitness|gym|wellness|doctor/.test(promptLower)) {
    return [
      { id: 'role_fitness_enthusiast', role: 'FITNESS ENTHUSIAST', description: 'Regular exerciser — validates core features.', count: 3, selected: true },
      { id: 'role_wellness_beginner', role: 'WELLNESS BEGINNER', description: 'Person starting health journey — tests onboarding.', count: 3, selected: true },
      { id: 'role_chronic_user', role: 'CHRONIC CONDITION USER', description: 'Managing health condition — tests specialized depth.', count: 3, selected: true },
      { id: 'role_skeptic', role: 'HEALTH APP SKEPTIC', description: 'Failed at health apps before — reveals churn drivers.', count: 0, selected: false },
    ];
  } else if (/payment|bank|finance|loan|invest|wallet|crypto/.test(promptLower)) {
    return [
      { id: 'role_early_adopter', role: 'EARLY ADOPTER PRO', description: 'Tech-savvy financial app user — validates core assumptions.', count: 3, selected: true },
      { id: 'role_small_biz', role: 'SMALL BUSINESS OWNER', description: 'SMB managing cash flow — high-value segment.', count: 3, selected: true },
      { id: 'role_underbanked', role: 'UNDERBANKED USER', description: 'Limited banking access — tests inclusion positioning.', count: 3, selected: true },
      { id: 'role_security_skeptic', role: 'SECURITY SKEPTIC', description: 'Privacy-first user — reveals trust barriers.', count: 0, selected: false },
    ];
  } else if (/shop|sell|buy|store|marketplace|ecommerce|fashion/.test(promptLower)) {
    return [
      { id: 'role_impulse_buyer', role: 'IMPULSE BUYER', description: 'Discovery-driven shopper — tests conversion.', count: 3, selected: true },
      { id: 'role_research_first', role: 'RESEARCH-FIRST BUYER', description: 'Methodical shopper — tests trust and clarity.', count: 3, selected: true },
      { id: 'role_loyal_repeater', role: 'LOYAL REPEATER', description: 'Returning customer — tests retention.', count: 3, selected: true },
      { id: 'role_premium_seeker', role: 'PREMIUM SEEKER', description: 'Quality-over-price buyer — tests premium positioning.', count: 0, selected: false },
    ];
  } else if (/saas|enterprise|team|workflow|b2b|productivity/.test(promptLower)) {
    return [
      { id: 'role_decision_maker', role: 'BUDGET DECISION MAKER', description: 'Manager who approves purchases — validates ROI.', count: 3, selected: true },
      { id: 'role_power_user', role: 'DAILY POWER USER', description: 'Heavy user — validates UX depth.', count: 3, selected: true },
      { id: 'role_it_eval', role: 'IT SECURITY EVALUATOR', description: 'Tech gatekeeping — tests compliance.', count: 3, selected: true },
      { id: 'role_resistant', role: 'CHANGE-RESISTANT USER', description: 'Reluctant adopter — reveals barriers.', count: 0, selected: false },
    ];
  } else if (/student|school|college|university|study/.test(promptLower)) {
    return [
      { id: 'role_uni_student', role: 'UNIVERSITY STUDENT', description: 'Core user — validates product-market fit.', count: 3, selected: true },
      { id: 'role_college_applicant', role: 'COLLEGE APPLICANT', description: 'High-stakes test-taker — validates premium tier.', count: 3, selected: true },
      { id: 'role_high_schooler', role: 'BUSY HIGH SCHOOLER', description: 'Time-pressed student — tests core value delivery.', count: 3, selected: true },
      { id: 'role_parental_buyer', role: 'PARENTAL BUYER', description: 'Parent paying for child — validates pricing framing.', count: 0, selected: false },
    ];
  }
  // Generic fallback
  return [
    { id: 'role_primary', role: 'PRIMARY USER', description: 'Core target user — validates product-market fit.', count: 3, selected: true },
    { id: 'role_early_adopter', role: 'EARLY ADOPTER', description: 'Forward-thinking user — validates initial demand.', count: 3, selected: true },
    { id: 'role_price_conscious', role: 'PRICE-CONSCIOUS USER', description: 'Budget-sensitive — validates pricing strategy.', count: 3, selected: true },
    { id: 'role_skeptic', role: 'SKEPTICAL USER', description: 'Using a competitor — reveals switching barriers.', count: 0, selected: false },
    { id: 'role_power_user', role: 'POWER USER', description: 'Heavy user — validates feature depth.', count: 0, selected: false },
  ];
}

/** Grounded mock personas for generateStudyPersonas in mock mode; registers
 * every persona in mockStore.personas exactly as the inlined original did. */
export function mockGeneratedPersonas(prompt?: string, title?: string): Persona[] {
  const promptLower = (prompt || title || '').toLowerCase();
  const isStudent = /student|school|college|university|study planner|academic|exam/.test(promptLower);
  const isPriceTracker = !isStudent && /price tracker|price-tracker|tracker|price track|deal alert|price drop|deal hunter|bargain|shopping|ecommerce/.test(promptLower);

  if (isPriceTracker) {
    const priceTrackerPersonas: Persona[] = [
      {
        id: 'per_samiul_alam',
        business_id: 'biz_default',
        name: 'Samiul Alam',
        initials: 'SA',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_bargain_hunter',
        role_title: 'Smart Bargain Hunter',
        archetype: 'Smart Bargain Hunter',
        tagline: 'The Strategic Deal Optimizer',
        demographics: {
          age: 26,
          gender: 'Male',
          occupation: 'Junior Software Engineer',
          income_bracket: '45,000 BDT/month',
          location: 'Dhaka (Mirpur), Bangladesh',
          education: 'B.Sc. in Computer Science',
        },
        description:
          'He frequently purchases electronics, accessories, and apparel online across Daraz, Pickaboo, and Facebook commerce. He actively waits for flash sales and wants historical price charts to avoid fake discount promotions.',
        badges: [
          { label: 'HOBBIES', value: 'tech gadgets, price comparison, gaming, cycling' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'MONTHLY E-COMMERCE SPEND', value: '4,000 - 8,000 BDT across gadget accessories & clothes' },
          { label: 'WILLINGNESS TO PAY', value: 'Finds 100 BDT/month fair if it saves at least 300 BDT per month in real discounts' },
          { label: 'PRIMARY ALERT CHANNEL', value: 'Telegram & WhatsApp instant notification' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Never Overpay on Online Gadgets',
            description: 'Track price history over 90 days to verify if sale discounts are authentic.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
          {
            category: 'Pain Points',
            title: 'Fake Markdown Prices & Lack of Alerts',
            description: 'Sellers artificially increase prices before sale campaigns. Manual checking wastes hours.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.99,
        grounding_ratio: 0.97,
        critic_notes: 'High consistency with young urban professional e-commerce consumer profile.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: new Date().toISOString(),
        status: 'active',
        version: 1,
      },
      {
        id: 'per_nabila_khan',
        business_id: 'biz_default',
        name: 'Nabila Khan',
        initials: 'NK',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_budget_planner',
        role_title: 'Budget-Conscious Buyer',
        archetype: 'Budget-Conscious Buyer',
        tagline: 'The Practical Household Economist',
        demographics: {
          age: 31,
          gender: 'Female',
          occupation: 'Digital Content Lead & Homemaker',
          income_bracket: '55,000 BDT/month household',
          location: 'Dhaka (Uttara), Bangladesh',
          education: 'BBA in Marketing',
        },
        description:
          'She manages household replenishment (skincare, pantry staples, baby products) and tracks price fluctuations across Chaldal, Daraz, and Shajgoj. She wants a single dashboard to alert her when favorite products hit their lowest price.',
        badges: [
          { label: 'HOBBIES', value: 'home organization, baking, lifestyle blogging' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'PURCHASE FREQUENCY', value: '3-4 online orders per week' },
          { label: 'PRICE TRACKING NEED', value: 'Bulk pantry staples, baby diapers, and imported cosmetic brands' },
          { label: 'PRICE TOLERANCE', value: 'Considers 100 BDT/month a no-brainer if it covers multiple e-commerce stores' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Streamlined Family Essentials Budget',
            description: 'Stock up on monthly staples at genuine price dips.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
          {
            category: 'Pain Points',
            title: 'Scattered Store Checking',
            description: 'Having to open 4 different apps to check who has the cheapest price.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'Accurate model of urban household digital shoppers in Bangladesh.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: new Date().toISOString(),
        status: 'active',
        version: 1,
      },
      {
        id: 'per_tanvir_hasan',
        business_id: 'biz_default',
        name: 'Tanvir Hasan',
        initials: 'TH',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_tech_shopper',
        role_title: 'Tech-Savvy Consumer',
        archetype: 'Tech-Savvy Consumer',
        tagline: 'The Analytical Deal Scout',
        demographics: {
          age: 23,
          gender: 'Male',
          occupation: '4th-year University Student & Freelancer',
          income_bracket: '18,000 BDT/month',
          location: 'Chattogram, Bangladesh',
          education: 'B.Sc. in Electrical Engineering',
        },
        description:
          'He freelances as a UI designer and is careful with discretionary spending. He bookmarks PC components and headphones, waiting for authentic price dips before buying.',
        badges: [
          { label: 'HOBBIES', value: 'PC building, graphic design, watching tech reviews' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'PAYMENT METHOD', value: 'bKash / Nagad mobile banking' },
          { label: 'SUBSCRIPTION VIEW', value: 'Prefers bKash recurring or micro-payment of 100 BDT rather than credit card requirement' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Automated Price Drop Threshold Alerts',
            description: 'Set custom price alerts (e.g. notify when price drops below 2,500 BDT).',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.97,
        grounding_ratio: 0.95,
        critic_notes: 'Young freelance tech buyer archetype verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: new Date().toISOString(),
        status: 'active',
        version: 1,
      },
    ];
    priceTrackerPersonas.forEach((p) => {
      mockStore.personas[p.id] = p;
    });
    return priceTrackerPersonas;
  }

  // Grounded mock personas matching datasets
  const defaultPersonas: Persona[] = [
    {
      id: 'per_nusrat_jahan',
      business_id: 'biz_default',
      name: 'Nusrat Jahan',
      initials: 'NJ',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_uni_student',
      role_title: 'University Student',
      archetype: 'University Student',
      tagline: 'The Frugal Striver',
      demographics: {
        age: 20,
        gender: 'Female',
        occupation: '2nd-year University Student',
        income_bracket: '7,500 BDT/mo Allowance',
        location: 'Rajshahi, Bangladesh',
        education: 'Undergraduate (Economics)',
      },
      description:
        'She is a second-year university student in Rajshahi who tries to stay organized without adding extra costs to her month. She takes her studies seriously and seeks affordable, practical digital tools.',
      badges: [
        { label: 'HOBBIES', value: 'reading Bangla fiction, watching study vlogs, casual badminton' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        {
          label: 'CLASS SCHEDULE',
          value: 'Five days a week with mostly morning and midday classes, plus lab sessions',
        },
        { label: 'MONTHLY ALLOWANCE', value: '7,500 BDT' },
        {
          label: 'EDUCATION APP USAGE',
          value: 'mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool',
        },
        { label: 'DEVICE ACCESS', value: 'mid-range Android smartphone and shared family laptop' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Coursework and Exam Organization',
          description:
            'Keep daily assignment deadlines, exam revision milestones, and club meetings synchronized.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
        {
          category: 'Pain Points',
          title: 'Overpriced Global Subscriptions',
          description:
            'Foreign SaaS tools require international credit cards and charge $10+/month which exceeds monthly allowance.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.98,
      grounding_ratio: 0.96,
      critic_notes: 'Highly consistent with Tier-2 university student budget profiles in Bangladesh.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_farzana_rahman',
      business_id: 'biz_default',
      name: 'Farzana Rahman',
      initials: 'FR',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_parental_planner',
      role_title: 'Parental Planner',
      archetype: 'Parental Planner',
      tagline: 'The Cost-Conscious Academic Guide',
      demographics: {
        age: 38,
        gender: 'Female',
        occupation: 'Homemaker & Study Supervisor',
        income_bracket: 'Middle Class Household',
        location: 'Rajshahi, Bangladesh',
        education: 'Masters in Social Sciences',
      },
      description:
        "She lives in Rajshahi with her family and takes an active role in keeping her children's school routine on track. She believes education is the safest long-term investment.",
      badges: [
        { label: 'HOBBIES', value: 'reading Bangla newspapers, balcony gardening, watching educational programs' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        { label: 'CHILD SCHOOL LEVEL', value: 'Secondary school (classes 8-10)' },
        {
          label: 'EDUCATION APP USAGE',
          value: 'mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool',
        },
        { label: 'MONTHLY STUDY BUDGET', value: '1,500 - 2,500 BDT for supplemental materials' },
        {
          label: 'DECISION FACTOR',
          value: 'Clear weekly progress tracking and direct alignment with NCTB board curriculum',
        },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Consistent Child Study Tracking',
          description: 'Help children build self-directed study habits without creating home tension.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.97,
      grounding_ratio: 0.95,
      critic_notes: 'Accurate representation of educated urban-adjacent parents in Bangladesh.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_tanjila_akter',
      business_id: 'biz_default',
      name: 'Tanjila Akter',
      initials: 'TA',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_college_applicant',
      role_title: 'College Applicant',
      archetype: 'College Applicant',
      tagline: 'The Structured Striver',
      demographics: {
        age: 18,
        gender: 'Female',
        occupation: 'HSC 2nd-Year & Admission Aspirant',
        income_bracket: '4,000 BDT/mo Allowance',
        location: 'Rajshahi, Bangladesh',
        education: 'Higher Secondary (Science)',
      },
      description:
        'She is an HSC student in Rajshahi preparing seriously for university admission exams and treats study time as a long-term investment in social mobility.',
      badges: [
        { label: 'HOBBIES', value: 'solving math problems, watching short educational videos, journaling' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        { label: 'CLASS LEVEL', value: 'HSC 2nd year (Science Track)' },
        {
          label: 'LEARNING TOOL USE',
          value: 'uses YouTube lessons, Facebook study groups, PDF notes, and mobile apps',
        },
        { label: 'MONTHLY ALLOWANCE', value: '4,000 BDT' },
        { label: 'ADMISSION TARGET', value: 'Public engineering and medical varsity admission seats' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Master High-Yield Admission Syllabus',
          description:
            'Systematically complete question banks and practice exams ahead of competitive admission deadlines.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.99,
      grounding_ratio: 0.97,
      critic_notes: 'Grounded in HSC science applicant behavioral datasets.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_mim_chowdhury',
      business_id: 'biz_default',
      name: 'Mim Chowdhury',
      initials: 'MC',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_budget_learner',
      role_title: 'Budget-Conscious Learner',
      archetype: 'Budget-Conscious Learner',
      tagline: 'The Resourceful Pragmatist',
      demographics: {
        age: 20,
        gender: 'Female',
        occupation: '2nd-year Degree Student',
        income_bracket: '3,000 BDT/mo Budget',
        location: 'Rangpur, Bangladesh',
        education: 'Undergraduate (National University)',
      },
      description:
        'She is a second-year student living in Rangpur while supporting family responsibilities and studying largely on her own schedule. She is careful with every taka.',
      badges: [
        { label: 'HOBBIES', value: 'reading Bengali novels, helping younger siblings with schoolwork, sketching' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        {
          label: 'INTERNET ACCESS',
          value: 'mostly mobile data with uneven speed; relies heavily on offline features',
        },
        {
          label: 'LEARNING TOOL USE',
          value: 'searches for free study templates, lecture summaries, and Telegram study groups',
        },
        { label: 'MONTHLY BUDGET', value: '200-300 BDT maximum for digital tools' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Maximize Exam Preparation on Low Budget',
          description: 'Obtain high exam marks without spending on expensive private tuitions.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.98,
      grounding_ratio: 0.96,
      critic_notes: 'Accurate reflection of divisional students with price sensitivity.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_sadia_sultana',
      business_id: 'biz_default',
      name: 'Sadia Sultana',
      initials: 'SS',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_high_schooler',
      role_title: 'Busy High Schooler',
      archetype: 'Busy High Schooler',
      tagline: 'The Structured Pragmatist',
      demographics: {
        age: 17,
        gender: 'Female',
        occupation: 'HSC 1st-Year Student',
        income_bracket: 'Dependent',
        location: 'Chattogram, Bangladesh',
        education: 'College (Class 11)',
      },
      description:
        'She is a 17-year-old higher secondary student in Chattogram balancing coursework, coaching, and extracurriculars while aiming for strong board exam GPA.',
      badges: [
        { label: 'HOBBIES', value: 'creative writing, watching science explainers, table tennis' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        { label: 'COACHING HOURS', value: '12 hours per week across science subjects' },
        {
          label: 'DEVICE ACCESS',
          value: 'owns a mid-range Android phone and shares a family laptop when needed',
        },
        { label: 'DAILY SCHEDULE', value: 'tight routine from 7 AM to 10 PM with coaching and school' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Balance Coaching and Self-Study',
          description: 'Sync heavy coaching center homework with daily self-study sessions.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.98,
      grounding_ratio: 0.96,
      critic_notes: 'High school science workload model verified.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_tasnia_islam',
      business_id: 'biz_default',
      name: 'Tasnia Islam',
      initials: 'TI',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_private_tutor_student',
      role_title: 'Private Tutor Student',
      archetype: 'Private Tutor Student',
      tagline: 'The Pragmatic Striver',
      demographics: {
        age: 20,
        gender: 'Female',
        occupation: '2nd-year BBA Student',
        income_bracket: '8,000 BDT/mo Allowance',
        location: 'Dhaka, Bangladesh',
        education: 'Undergraduate (BBA)',
      },
      description:
        'She is a second-year university student in Dhaka balancing coursework, family expectations, and a tight monthly budget. She likes organized routines.',
      badges: [
        { label: 'HOBBIES', value: 'reading class notes with friends, watching Bangla and Korean dramas' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        {
          label: 'LEARNING ROUTINE',
          value: 'studies most evenings, reviews lecture notes before quizzes, and intensifies before finals',
        },
        { label: 'LIVING SETUP', value: 'lives with family and commutes to campus via rickshaw and bus' },
        { label: 'TUTORING SUPPORT', value: 'receives weekly private tutoring in mathematics and statistics' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Track Private Tutoring Assignments',
          description: 'Organize weekly tasks assigned by private tutors and university professors in one place.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.97,
      grounding_ratio: 0.95,
      critic_notes: 'Dhaka commuter and private tutoring user profile verified.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_rafia_karim',
      business_id: 'biz_default',
      name: 'Rafia Karim',
      initials: 'RK',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_scholarship_aspirant',
      role_title: 'Scholarship Aspirant',
      archetype: 'Scholarship Aspirant',
      tagline: 'The Structured Climber',
      demographics: {
        age: 19,
        gender: 'Female',
        occupation: 'Admission Candidate',
        income_bracket: 'Dependent',
        location: 'Chattogram, Bangladesh',
        education: 'HSC Graduate (Science)',
      },
      description:
        'She is a scholarship-focused student from Chattogram who treats study time as a long-term investment and prefers structure over guesswork. She is ambitious and disciplined.',
      badges: [
        { label: 'HOBBIES', value: 'solving math puzzles, journaling, debate club, watching educational YouTube' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        { label: 'COACHING FORMAT', value: 'hybrid coaching center plus self-study with online supplements' },
        { label: 'EXAM STAGE', value: 'university admission preparation with scholarship focus' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'High-Percentile Exam Benchmarking',
          description: 'Track mock test accuracy rates and time management across every question chapter.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.99,
      grounding_ratio: 0.97,
      critic_notes: 'High ambition scholarship seeker profile verified.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_mahin_hossain',
      business_id: 'biz_default',
      name: 'Mahin Hossain',
      initials: 'MH',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_group_organizer',
      role_title: 'Study Group Organizer',
      archetype: 'Study Group Organizer',
      tagline: 'The Quiet Systems Builder',
      demographics: {
        age: 21,
        gender: 'Male',
        occupation: '3rd-year CSE Student',
        income_bracket: '6,000 BDT/mo Allowance + Tuitions',
        location: 'Rajshahi, Bangladesh',
        education: 'Undergraduate (Computer Science)',
      },
      description:
        'He is a third-year university student in Rajshahi who quietly became the person classmates rely on to keep group study on track. He prefers structured routines, low fuss.',
      badges: [
        {
          label: 'HOBBIES',
          value: 'badminton, football highlights, nonfiction reading, tidy note-making, and casual coding',
        },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        {
          label: 'DIGITAL STUDY TOOLS',
          value: 'WhatsApp, Google Calendar, Google Drive, Facebook Messenger, and a study app',
        },
        { label: 'GROUP SIZE', value: '6 students in his core study circle' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Coordinate Group Project Schedules',
          description: 'Coordinate group study sessions, lab project sprints, and exam question distributions.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.98,
      grounding_ratio: 0.96,
      critic_notes: 'Group leader persona verified against campus cohort behavioral datasets.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_samia_tabassum',
      business_id: 'biz_default',
      name: 'Samia Tabassum',
      initials: 'ST',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_test_prep',
      role_title: 'Test Prep Seeker',
      archetype: 'Test Prep Seeker',
      tagline: 'The Disciplined Value-Seeker',
      demographics: {
        age: 17,
        gender: 'Female',
        occupation: 'Class 11 Science Student',
        income_bracket: 'Dependent',
        location: 'Chattogram, Bangladesh',
        education: 'College (HSC 1st year)',
      },
      description:
        'She is a Class 11 science student in Chattogram who attends several private tutoring sessions each week and relies on careful routines to stay on top of exams.',
      badges: [
        { label: 'HOBBIES', value: 'mobile photography, watching cricket highlights, solving puzzle apps, and walking' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        {
          label: 'DIGITAL TOOL USE',
          value: 'uses YouTube lectures, Facebook study groups, shared PDF notes, and occasional practice apps',
        },
        { label: 'MONTHLY STUDY BUDGET', value: '300-500 taka/month for optional study aids beyond tutor fees' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Consistent Chapter Revision Cycles',
          description: 'Build repeated spaced repetition cycles before monthly college exams.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.98,
      grounding_ratio: 0.96,
      critic_notes: 'Class 11 test prep discipline model verified.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
    {
      id: 'per_iffat_ara',
      business_id: 'biz_default',
      name: 'Iffat Ara',
      initials: 'IA',
      country_code: 'BD',
      country_name: 'Bangladesh',
      role_id: 'role_remote_student',
      role_title: 'Remote Student',
      archetype: 'Remote Student',
      tagline: 'The Resourceful Skeptic',
      demographics: {
        age: 18,
        gender: 'Female',
        occupation: 'Science-track College Applicant',
        income_bracket: 'Dependent',
        location: 'Rajshahi, Bangladesh',
        education: 'HSC (Science)',
      },
      description:
        'She is an 18-year-old science-track college applicant in Rajshahi aiming for a public university seat. Careful with money and sensitive to academic pressure, she already uses free tools.',
      badges: [
        { label: 'HOBBIES', value: 'solving math problems, watching cricket highlights, reading Bengali short stories' },
        { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
        { label: 'COACHING STATUS', value: 'enrolled in a local offline coaching center with online test series' },
        { label: 'DEVICE ACCESS', value: 'own Android smartphone with mobile data connectivity' },
      ],
      attributes: [
        {
          category: 'Goals',
          title: 'Reliable Offline Study Planning',
          description: 'Access revision schedules and practice notes even during poor internet connectivity.',
          provenance_class: 'OBSERVED',
          evidence: null,
        },
      ],
      consistency_score: 0.97,
      grounding_ratio: 0.95,
      critic_notes: 'Remote connectivity and price skepticism persona verified.',
      generation_model: 'bebshax/dataset-grounded-v2',
      created_at: '2026-08-24T22:00:00Z',
      status: 'active',
      version: 1,
    },
  ];

  defaultPersonas.forEach((p) => {
    mockStore.personas[p.id] = p;
  });

  return defaultPersonas;
}
