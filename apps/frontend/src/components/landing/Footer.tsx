import React, { useState } from 'react';
import { LegalModal } from '../auth/LegalModal';

export const Footer: React.FC = () => {
  const [legal, setLegal] = useState<'terms' | 'privacy' | null>(null);

  const links = [
    { label: 'Workspace', href: '#product' },
    { label: 'How it works', href: '#how-it-works' },
    { label: 'Research integrity', href: '#integrity' },
    { label: 'Pricing', href: '#pricing' },
    { label: 'FAQ', href: '#faq' },
  ];

  return (
    <footer className="studio-footer">
      <div className="studio-container">
        <div className="studio-footer-top">
          <div>
            <a className="studio-brand" href="#top" aria-label="BebshaX home">
              <img src="/logobebshax.jpeg" alt="" width="28" height="28" /><span>BebshaX</span>
            </a>
            <p>Synthetic research. Human judgment.</p>
          </div>
          <nav aria-label="Footer navigation">
            {links.map((link) => <a key={link.href} href={link.href}>{link.label}</a>)}
          </nav>
        </div>
        <div className="studio-footer-bottom">
          <p>&copy; {new Date().getFullYear()} BebshaX</p>
          <div className="studio-legal-links">
            <button type="button" onClick={(event) => { event.currentTarget.focus(); setLegal('terms'); }}>Terms of Service</button>
            <button type="button" onClick={(event) => { event.currentTarget.focus(); setLegal('privacy'); }}>Privacy Policy</button>
          </div>
        </div>
      </div>
      {legal && (
        <div className="studio-legal">
          <LegalModal isOpen onClose={() => setLegal(null)} type={legal} />
        </div>
      )}
    </footer>
  );
};
