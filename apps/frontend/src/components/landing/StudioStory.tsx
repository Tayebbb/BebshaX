import React from 'react';
import { ArrowUpRight, FileText, MessageSquare, ScanText, Users } from 'lucide-react';
import workspaceImage from './research-workspace.png';

export const ProductStory: React.FC = () => (
  <section id="product" className="studio-product" aria-labelledby="studio-product-title" tabIndex={-1}>
    <div className="studio-container">
      <h2 id="studio-product-title">A workspace for the questions that come before the product.</h2>
      <figure className="studio-product-figure">
        <a href={workspaceImage} target="_blank" rel="noopener noreferrer" className="studio-image-link"
          aria-label="View the full-size SAMPLE workspace screenshot">
          <img src={workspaceImage} width="1440" height="1000" loading="eager"
            alt="BebshaX research workspace with a study brief and research options. SAMPLE synthetic research, not observed customer data." />
        </a>
        <figcaption>
          <span><strong>SAMPLE</strong> workspace capture with synthetic data, not observed customer research.</span>
          <a href={workspaceImage} target="_blank" rel="noopener noreferrer">View full size <ArrowUpRight size={16} aria-hidden="true" /></a>
        </figcaption>
      </figure>
    </div>
  </section>
);

const workflow = [
  { title: 'Start with a question.', icon: ScanText, description: 'Shape your idea into a research goal. Decide which assumptions you need to explore.' },
  { title: 'Meet a synthetic audience.', icon: Users, description: 'Review source-selected personas and their provenance. Keep the sample limitations in view.' },
  { title: 'Follow the conversation.', icon: MessageSquare, description: 'Edit your interview script, ask follow-ups, and revisit the saved transcript.' },
  { title: 'Take the questions forward.', icon: FileText, description: 'Bring the report and its open questions into your next round of research with real people.' },
];

export const StudyWorkflow: React.FC = () => (
  <section id="how-it-works" className="studio-section studio-workflow" aria-label="How it works" tabIndex={-1}>
    <div className="studio-container">
      <div className="studio-section-heading">
        <h2>From a question to a research trail.</h2>
        <p>A connected study, from the first brief to the interview and report.</p>
      </div>
      <ol className="studio-workflow-list">
        {workflow.map(({ title, icon: Icon, description }) => (
          <li key={title}>
            <Icon size={25} strokeWidth={1.6} aria-hidden="true" />
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
        <h2 id="studio-integrity-title">Useful questions.<br />Honest boundaries.</h2>
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