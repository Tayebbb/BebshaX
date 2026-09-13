import React from 'react';
import { useRouteReady } from '../../performance/routeTiming';
import { Navbar } from './Navbar';
import { Hero } from './Hero';
import { ProductStory, ResearchIntegrity, StudyWorkflow } from './StudioStory';
import { FAQ } from './FAQ';
import { Pricing } from './Pricing';
import { FinalCTA } from './FinalCTA';
import { Footer } from './Footer';
import './studio.css';

interface LandingPageProps {
  onOpenApp: () => void;
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onOpenApp, onOpenAuth }) => {
  useRouteReady(true);
  return (
    <div className="studio-landing">
      <a className="studio-skip" href="#studio-main">Skip to content</a>
      <Navbar onOpenApp={onOpenApp} onOpenAuth={onOpenAuth} />
      <main id="studio-main" aria-label="BebshaX synthetic persona research" tabIndex={-1}>
        <Hero onOpenApp={onOpenApp} />
        <ProductStory />
        <StudyWorkflow />
        <ResearchIntegrity />
        <Pricing onOpenAuth={onOpenAuth} />
        <FAQ />
        <FinalCTA onOpenApp={onOpenApp} />
      </main>
      <Footer />
    </div>
  );
};
