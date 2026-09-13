import React from 'react';
import { ArrowUpRight } from 'lucide-react';

export { ProductGallery as ProductStory } from './ProductGallery';

const workflow = [
  { title: 'Write the brief.', description: 'One idea, one audience, one uncertainty. Pick the study type that fits the question.' },
  { title: 'Review the personas.', description: 'Keep the profiles that match your audience. Every card says what is synthetic and what has a source.' },
  { title: 'Run the interviews.', description: 'Edit the script, ask follow-ups, and read the transcript. Each turn keeps its provenance.' },
  { title: 'Hand off the report.', description: 'Export the findings and the open questions to your next round with real participants.' },
];

export const StudyWorkflow: React.FC = () => (
  <section id="how-it-works" className="studio-section studio-workflow" aria-label="How it works" tabIndex={-1}>
    <div className="studio-container">
      <div className="studio-section-heading">
        <h2>From a question to a research trail.</h2>
        <p>Four steps. Each one leaves a record you can check later.</p>
      </div>
      <ol className="studio-workflow-list">
        {workflow.map(({ title, description }) => (
          <li key={title}>
            <h3>{title}</h3>
            <p>{description}</p>
          </li>
        ))}
      </ol>
    </div>
  </section>
);

export const ResearchIntegrity: React.FC = () => (
  <section id="integrity" className="studio-section studio-integrity" aria-labelledby="studio-integrity-title" tabIndex={-1}>
    <div className="studio-container studio-integrity-grid">
      <div className="studio-integrity-copy">
        <h2 id="studio-integrity-title">Useful questions. Honest boundaries.</h2>
        <p>Synthetic personas are not real participants or validated demand.</p>
        <p>Use simulated conversations to sharpen a hypothesis, not to claim you have proven it. Sources and assumptions stay distinct.</p>
        <a className="studio-text-link" href="#faq">Read the research limitations <ArrowUpRight size={17} aria-hidden="true" /></a>
      </div>
      <dl className="studio-provenance">
        <div>
          <dt>Synthetic</dt>
          <dd>A selected synthetic source profile or simulated response. It is not an observation about a real customer.</dd>
        </div>
        <div>
          <dt>Inferred</dt>
          <dd>An interpretation drawn from the available material. Treat it as a hypothesis to investigate.</dd>
        </div>
        <div>
          <dt>Observed</dt>
          <dd>A claim with a retrieved record cited as evidence. A citation alone does not establish that the claim is true.</dd>
        </div>
      </dl>
    </div>
  </section>
);