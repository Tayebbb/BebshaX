import React from 'react';

interface BebshaXLogoProps {
  size?: number;
  showText?: boolean;
  textSize?: string;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  variant?: 'hexagon-cube' | 'diamond-nexus' | 'orbit-delta';
}

export const BebshaXLogo: React.FC<BebshaXLogoProps> = ({
  size = 28,
  showText = true,
  textSize = '1.2rem',
  className,
  style,
  onClick,
  variant = 'hexagon-cube',
}) => {
  return (
    <div
      className={className}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '10px',
        cursor: onClick ? 'pointer' : 'default',
        textDecoration: 'none',
        userSelect: 'none',
        ...style,
      }}
    >
      {/* Dynamic Geometric Node Network Icon */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ flexShrink: 0, overflow: 'visible' }}
      >
        <defs>
          <linearGradient id="goldStroke" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FDE68A" />
            <stop offset="50%" stopColor="#F6C878" />
            <stop offset="100%" stopColor="#D4AF37" />
          </linearGradient>
          <linearGradient id="goldGlow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FFFBEB" />
            <stop offset="100%" stopColor="#F6C878" />
          </linearGradient>
          <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="0.8" />
            <feMerge>
              <feMergeNode />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {variant === 'hexagon-cube' && (
          // Isometric 3D Hexagonal Node Lattice
          <g>
            {/* Outer Hexagon Edges */}
            <polygon
              points="16,3 27.5,9.5 27.5,22.5 16,29 4.5,22.5 4.5,9.5"
              stroke="url(#goldStroke)"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {/* Internal Isometric Y-Axis & X Connectors */}
            <line x1="16" y1="3" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="27.5" y1="22.5" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="4.5" y1="22.5" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="2.2" strokeLinecap="round" />

            {/* Accent Diagonal Cross Links (Subtle depth) */}
            <line x1="27.5" y1="9.5" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="1.2" strokeDasharray="2 2" opacity="0.65" />
            <line x1="4.5" y1="9.5" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="1.2" strokeDasharray="2 2" opacity="0.65" />
            <line x1="16" y1="29" x2="16" y2="16" stroke="url(#goldStroke)" strokeWidth="1.2" strokeDasharray="2 2" opacity="0.65" />

            {/* Perimeter Vertex Nodes */}
            <circle cx="16" cy="3" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="27.5" cy="9.5" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="27.5" cy="22.5" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="29" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="4.5" cy="22.5" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="4.5" cy="9.5" r="2.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />

            {/* Central Nexus Core Node */}
            <circle cx="16" cy="16" r="3.2" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="16" r="1.4" fill="#080909" />
          </g>
        )}

        {variant === 'diamond-nexus' && (
          // Diamond / Rhombus 4-Node Nexus
          <g>
            <polygon
              points="16,2.5 29,16 16,29.5 3,16"
              stroke="url(#goldStroke)"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <line x1="16" y1="2.5" x2="16" y2="29.5" stroke="url(#goldStroke)" strokeWidth="2" strokeLinecap="round" />
            <line x1="3" y1="16" x2="29" y2="16" stroke="url(#goldStroke)" strokeWidth="2" strokeLinecap="round" />

            <circle cx="16" cy="2.5" r="2.5" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="29" cy="16" r="2.5" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="29.5" r="2.5" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="3" cy="16" r="2.5" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="16" r="3.4" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="16" r="1.5" fill="#080909" />
          </g>
        )}

        {variant === 'orbit-delta' && (
          // Delta Orbital with Double Node Wings
          <g>
            <polygon
              points="16,3.5 28.5,26.5 3.5,26.5"
              stroke="url(#goldStroke)"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <line x1="16" y1="3.5" x2="16" y2="18.5" stroke="url(#goldStroke)" strokeWidth="2" />
            <line x1="3.5" y1="26.5" x2="16" y2="18.5" stroke="url(#goldStroke)" strokeWidth="2" />
            <line x1="28.5" y1="26.5" x2="16" y2="18.5" stroke="url(#goldStroke)" strokeWidth="2" />

            <circle cx="16" cy="3.5" r="2.6" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="28.5" cy="26.5" r="2.6" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="3.5" cy="26.5" r="2.6" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
            <circle cx="16" cy="18.5" r="3.2" fill="url(#goldGlow)" filter="url(#nodeGlow)" />
          </g>
        )}
      </svg>

      {/* Brand Text */}
      {showText && (
        <span
          aria-label="BebshaX"
          style={{
            fontSize: textSize,
            fontWeight: 700,
            letterSpacing: '-0.03em',
            color: '#FFFFFF',
            display: 'inline-flex',
            alignItems: 'baseline',
          }}
        >
          BebshaX
        </span>
      )}
    </div>
  );
};
