import React from 'react';
import { ArrowDown, ArrowRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface HeroProps {
  onOpenApp?: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onOpenApp }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();

  const openWorkspace = () => {
    if (onOpenApp) onOpenApp();
    else navigate(isAuthenticated ? '/app' : '/auth/signin');
  };

  return (
    <section id="top" className="studio-hero" aria-labelledby="studio-title">
      <div className="studio-container studio-hero-copy">
        <h1 id="studio-title">
          <span className="studio-hero-brand">BebshaX.</span>{' '}
          <span>Synthetic persona research.</span>
        </h1>
        <p>Develop hypotheses to test with real people.</p>
        <div className="studio-actions">
          <button type="button" className="studio-button" onClick={openWorkspace}>
            Open workspace <ArrowRight size={18} aria-hidden="true" />
          </button>
          <a className="studio-text-link" href="#product">
            Explore the workspace <ArrowDown size={17} aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>
  );
};
