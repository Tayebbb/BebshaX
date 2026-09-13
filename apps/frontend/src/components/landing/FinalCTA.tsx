import React from 'react';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface FinalCTAProps {
  onOpenApp?: () => void;
}

export const FinalCTA: React.FC<FinalCTAProps> = ({ onOpenApp }) => {
  const { isAuthenticated } = useAuth();
  const { navigate } = useNavigation();

  const handlePrimaryAction = () => {
    if (onOpenApp) onOpenApp();
    else navigate(isAuthenticated ? '/app' : '/auth/signin');
  };

  return (
    <section id="start" className="studio-section studio-closing" aria-labelledby="studio-closing-title" tabIndex={-1}>
      <div className="studio-container">
        <h2 id="studio-closing-title">Bring your next question.</h2>
        <p>Start a study and keep the assumptions in view.</p>
        <button type="button" className="studio-button" onClick={handlePrimaryAction}>
          Open workspace <ArrowRight size={18} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
};
