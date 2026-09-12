import React from 'react';
import { ChevronDown } from 'lucide-react';

export const FAQ: React.FC = () => {
  const faqs = [
    {
      q: 'What is a synthetic persona in BebshaX?',
      a: 'A profile selected from a synthetic source dataset for your study context. You can review it and use it in simulated interviews. It is not a recruited participant, a population estimate, or evidence of customer demand.',
    },
    {
      q: 'Can this replace research with real people?',
      a: 'No. Synthetic interviews can help you explore assumptions and prepare better questions. Validate important findings with real participants and relevant evidence before making consequential decisions. Source coverage is limited and may not represent your market.',
    },
    {
      q: 'What happens when a provider is unavailable?',
      a: 'Eligible requests can move from the primary remote provider pool to a secondary route under the same quality policy. Persona context is not silently shortened to make a request fit. If no suitable route can serve it, the operation reports a failure. Availability and free-tier quotas apply; live interviews are not guaranteed offline.',
    },
    {
      q: 'What should I bring to my first study?',
      a: 'A product or business idea and a question you want to investigate. The study connects your goal, synthetic personas, an editable script, interviews, and a report. Use synthetic or non-sensitive descriptions; do not submit personal information or confidential material to remote inference providers.',
    },
    {
      q: 'Are language models trained on my studies?',
      a: 'BebshaX does not fine-tune language models. Its separate CPU persona selector is trained only on approved public synthetic datasets, not private studies or conversations. Remote providers have their own data policies, so keep submitted material non-sensitive.',
    },
  ];

  return (
    <section id="faq" className="studio-section studio-faq" aria-labelledby="studio-faq-title" tabIndex={-1}>
      <div className="studio-container studio-faq-content">
        <h2 id="studio-faq-title">A few important answers.</h2>
        <div className="studio-questions">
          {faqs.map((faq) => (
            <details key={faq.q}>
              <summary>{faq.q}<ChevronDown size={18} aria-hidden="true" /></summary>
              <p>{faq.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
};
