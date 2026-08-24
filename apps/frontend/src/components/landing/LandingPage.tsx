import React from 'react';
import { AnimatedBackground } from './AnimatedBackground';
import { Navbar } from './Navbar';
import { Hero } from './Hero';
import { HeroDashboardSection } from './HeroDashboardSection';
import { TrustMetrics } from './TrustMetrics';
import { ProblemSection } from './ProblemSection';
import { HowItWorks } from './HowItWorks';
import { ProductShowcase } from './ProductShowcase';
import { IntelligenceSection } from './IntelligenceSection';
import { FeatureGrid } from './FeatureGrid';
import { Comparison } from './Comparison';
import { InteractiveDemo } from './InteractiveDemo';
import { UseCases } from './UseCases';
import { Testimonials } from './Testimonials';
import { FAQ } from './FAQ';
import { FinalCTA } from './FinalCTA';
import { Footer } from './Footer';

interface LandingPageProps {
  onOpenApp: () => void;
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onOpenApp, onOpenAuth }) => {
  return (
    <div
      style={{
        position: 'relative',
        minHeight: '100vh',
        background: '#000000',
        color: '#FFFFFF',
        overflowX: 'hidden',
      }}
    >
      {/* Background Interactive Data Grid Canvas - Confined to Hero 100vh Fold */}
      <AnimatedBackground />

      {/* Navigation */}
      <Navbar onOpenApp={onOpenApp} onOpenAuth={onOpenAuth} />

      {/* Main Content Sections */}
      <main style={{ position: 'relative', zIndex: 1 }}>
        {/* 1st Screen Hero Fold Matching Image 1 */}
        <Hero onOpenApp={onOpenApp} />

        {/* Dashboard Preview Section (Image 2) Visible When Scrolling Down */}
        <HeroDashboardSection />

        <TrustMetrics />
        <ProblemSection />
        <HowItWorks />
        <ProductShowcase />
        <IntelligenceSection />
        <FeatureGrid />
        <Comparison />
        <InteractiveDemo />
        <UseCases />
        <Testimonials />
        <FAQ />
        <FinalCTA onOpenApp={onOpenApp} />
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
};
