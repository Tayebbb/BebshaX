import React, { useId, useRef, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import studyBrief from './gallery/study-brief.png';
import personaLibrary from './gallery/persona-library.png';
import interviewStep from './gallery/interview-step.png';
import workspaceMobileImage from './research-workspace-mobile.png';

interface GalleryView {
  id: string;
  label: string;
  title: string;
  description: string;
  image: string;
  alt: string;
}

// Real Edge captures of the mock preview; SAMPLE synthetic data only.
const views: GalleryView[] = [
  {
    id: 'brief',
    label: 'Brief',
    title: 'Start with the question.',
    description: 'Describe the idea, the audience, and the uncertainty. The study type shapes what the personas are asked.',
    image: studyBrief,
    alt: 'BebshaX research workspace with a study brief and research options. SAMPLE synthetic research, not observed customer data.',
  },
  {
    id: 'personas',
    label: 'Personas',
    title: 'Meet a synthetic audience.',
    description: 'Source-selected profiles with traits, goals, and frictions. Every card names what is synthetic.',
    image: personaLibrary,
    alt: 'BebshaX persona library showing synthetic persona cards with traits and goals. SAMPLE synthetic research, not observed customer data.',
  },
  {
    id: 'interviews',
    label: 'Interviews',
    title: 'Follow the conversation.',
    description: 'Multi-turn interviews per persona, with objectives, turn counts, and a transcript to revisit.',
    image: interviewStep,
    alt: 'BebshaX interview lab listing completed synthetic persona interviews. SAMPLE synthetic research, not observed customer data.',
  },
];

export const ProductGallery: React.FC = () => {
  const [active, setActive] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const baseId = useId();
  const view = views[active];

  const focusTab = (index: number) => {
    const next = (index + views.length) % views.length;
    setActive(next);
    tabRefs.current[next]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys: Record<string, () => void> = {
      ArrowRight: () => focusTab(index + 1),
      ArrowLeft: () => focusTab(index - 1),
      Home: () => focusTab(0),
      End: () => focusTab(views.length - 1),
    };
    const handler = keys[event.key];
    if (!handler) return;
    event.preventDefault();
    handler();
  };

  return (
    <section id="product" className="studio-product" aria-labelledby="studio-product-title" tabIndex={-1}>
      <div className="studio-container">
        <div className="studio-section-heading studio-product-heading">
          <h2 id="studio-product-title">One connected study.</h2>
          <p>The brief, the personas, and the interviews live in one place, and every claim shows where it came from.</p>
        </div>
        <div className="studio-gallery">
          <div className="studio-gallery-tabs" role="tablist" aria-label="Product views">
            {views.map((item, index) => (
              <button
                key={item.id}
                ref={(element) => { tabRefs.current[index] = element; }}
                type="button"
                role="tab"
                id={`${baseId}-tab-${item.id}`}
                aria-selected={index === active}
                aria-controls={`${baseId}-panel-${item.id}`}
                tabIndex={index === active ? 0 : -1}
                className="studio-gallery-tab"
                onClick={() => setActive(index)}
                onKeyDown={(event) => onKeyDown(event, index)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`${baseId}-panel-${view.id}`}
            aria-labelledby={`${baseId}-tab-${view.id}`}
            className="studio-gallery-panel"
          >
            <div className="studio-gallery-copy">
              <h3>{view.title}</h3>
              <p>{view.description}</p>
            </div>
            <figure className="studio-product-figure">
              <a href={view.image} target="_blank" rel="noopener noreferrer" className="studio-image-link"
                aria-label={`View the full-size SAMPLE ${view.label.toLowerCase()} screenshot`}>
                <picture>
                  {active === 0 && <source media="(max-width: 40rem)" srcSet={workspaceMobileImage} width="390" height="844" />}
                  <img key={view.id} src={view.image} width="1200" height="1000" loading={active === 0 ? 'eager' : 'lazy'} alt={view.alt} />
                </picture>
              </a>
              <figcaption>
                <span><strong>SAMPLE</strong> workspace capture with synthetic data, not observed customer research.</span>
                <a href={view.image} target="_blank" rel="noopener noreferrer">View full size <ArrowUpRight size={16} aria-hidden="true" /></a>
              </figcaption>
            </figure>
          </div>
        </div>
      </div>
    </section>
  );
};
