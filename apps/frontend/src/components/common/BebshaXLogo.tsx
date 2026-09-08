import React from 'react';
import { useTheme } from '../../context/ThemeContext';

interface BebshaXLogoProps {
  size?: number;
  showText?: boolean;
  textSize?: string;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  variant?: 'hexagon-cube' | 'diamond-nexus' | 'orbit-delta';
  useImageWordmark?: boolean;
}

export const BebshaXLogo: React.FC<BebshaXLogoProps> = ({
  size = 28,
  showText = true,
  className,
  style,
  onClick,
  useImageWordmark = true,
}) => {
  let isLight = false;
  try {
    const { theme } = useTheme();
    isLight = theme === 'light';
  } catch {
    isLight = typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'light';
  }

  const iconRadius = Math.max(4, Math.round(size * 0.22));

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
      {/* Official BebshaX Geometric B Logo Mark */}
      <img
        src="/logobebshax.jpeg"
        alt="BebshaX Logo"
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: `${iconRadius}px`,
          objectFit: 'contain',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
        }}
      />

      {/* Brand Wordmark */}
      {showText && (
        <div style={{ display: 'inline-flex', alignItems: 'center' }}>
          {useImageWordmark ? (
            <img
              src="/Bebshax.png"
              alt="BebshaX"
              style={{
                height: `${Math.round(size * 0.85)}px`,
                objectFit: 'contain',
                filter: isLight ? 'none' : 'brightness(0) invert(1)',
                transition: 'filter 0.2s ease',
              }}
            />
          ) : (
            <span
              style={{
                fontSize: `${size * 0.55}px`,
                fontWeight: 700,
                letterSpacing: '-0.03em',
                color: 'var(--text-main)',
              }}
            >
              BebshaX
            </span>
          )}
          {/* Accessible text for screen readers and unit tests */}
          <span
            style={{
              position: 'absolute',
              width: '1px',
              height: '1px',
              padding: 0,
              margin: '-1px',
              overflow: 'hidden',
              clip: 'rect(0, 0, 0, 0)',
              whiteSpace: 'nowrap',
              border: 0,
            }}
          >
            BebshaX
          </span>
        </div>
      )}
    </div>
  );
};
