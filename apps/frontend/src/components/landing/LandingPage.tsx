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
import { FAQ } from './FAQ';
import { Pricing } from './Pricing';
import { FinalCTA } from './FinalCTA';
import { Footer } from './Footer';
import { Reveal } from './Reveal';
import './landing.css';

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
        background: '#080909',
        color: '#FFFFFF',
        overflowX: 'hidden',
      }}
    >
      {/* Evidence Constellation — living environment of the hero fold */}
      <AnimatedBackground />

      {/* Navigation */}
      <Navbar onOpenApp={onOpenApp} onOpenAuth={onOpenAuth} />

      {/* Scenes. The dashboard preview rises masked out of the hero's exit;
          everything below the second fold defers rendering until approached. */}
      <main style={{ position: 'relative', zIndex: 1 }}>
        <Hero onOpenApp={onOpenApp} />

        <Reveal variant="mask">
          <HeroDashboardSection />
        </Reveal>

        <div className="lp-defer">
          <Reveal variant="rise"><TrustMetrics /></Reveal>
          <Reveal variant="rise"><ProblemSection /></Reveal>
          <Reveal variant="rise"><HowItWorks /></Reveal>
          <Reveal variant="rise"><ProductShowcase /></Reveal>
          <Reveal variant="rise"><IntelligenceSection /></Reveal>
          <Reveal variant="rise"><FeatureGrid /></Reveal>
          <Reveal variant="rise"><Comparison /></Reveal>
          <Reveal variant="rise"><InteractiveDemo onOpenApp={onOpenApp} /></Reveal>
          <Reveal variant="rise"><UseCases /></Reveal>
          <Reveal variant="rise"><FAQ /></Reveal>
          <Reveal variant="rise"><Pricing onOpenAuth={onOpenAuth} /></Reveal>
          <Reveal variant="mask"><FinalCTA onOpenApp={onOpenApp} /></Reveal>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
};
