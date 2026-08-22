import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { RoutingDashboardView } from './views/RoutingDashboardView';
import { BusinessSetupView } from './views/BusinessSetupView';
import { PersonaProfileView } from './views/PersonaProfileView';
import { PersonaMemoryView } from './views/PersonaMemoryView';
import { InterviewChatView } from './views/InterviewChatView';
import { EvaluationInsightsView } from './views/EvaluationInsightsView';

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<string>('routing');
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>('per_sarah_01');
  const [selectedBusinessId, setSelectedBusinessId] = useState<string>('biz_fintech_01');

  const handleSelectBusiness = (businessId: string) => {
    setSelectedBusinessId(businessId);
    setCurrentView('personas');
  };

  const handleNavigateToMemory = (personaId: string) => {
    setSelectedPersonaId(personaId);
    setCurrentView('memory');
  };

  const handleNavigateToInterview = (personaId: string) => {
    setSelectedPersonaId(personaId);
    setCurrentView('interviews');
  };

  return (
    <div className="app-container">
      <Sidebar currentView={currentView} onSelectView={setCurrentView} />

      <div className="main-content">
        <Navbar currentView={currentView} />

        <main className="view-content">
          {currentView === 'routing' && <RoutingDashboardView />}

          {currentView === 'businesses' && (
            <BusinessSetupView onSelectBusiness={handleSelectBusiness} />
          )}

          {currentView === 'personas' && (
            <PersonaProfileView
              initialBusinessId={selectedBusinessId}
              onNavigateToMemory={handleNavigateToMemory}
              onNavigateToInterview={handleNavigateToInterview}
            />
          )}

          {currentView === 'memory' && (
            <PersonaMemoryView initialPersonaId={selectedPersonaId} />
          )}

          {currentView === 'interviews' && (
            <InterviewChatView initialPersonaId={selectedPersonaId} />
          )}

          {currentView === 'evaluation' && <EvaluationInsightsView />}
        </main>
      </div>
    </div>
  );
};

export default App;
