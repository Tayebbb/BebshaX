import React from 'react';

interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  shape?: 'line' | 'block' | 'circle';
  className?: string;
  style?: React.CSSProperties;
}

/** Shape-true loading placeholder. Shimmer is disabled under reduced motion (index.css). */
export const Skeleton: React.FC<SkeletonProps> = ({ width = '100%', height, shape = 'line', className, style }) => (
  <div
    aria-hidden="true"
    className={`bx-skeleton bx-skel-${shape}${className ? ` ${className}` : ''}`}
    style={{ width, height: height ?? (shape === 'line' ? 12 : shape === 'circle' ? width : 80), ...style }}
  />
);

/** A stack of lines that reads like a paragraph while text loads. */
export const SkeletonText: React.FC<{ lines?: number; className?: string }> = ({ lines = 3, className }) => (
  <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: 8 }} aria-hidden="true">
    {Array.from({ length: lines }).map((_, i) => (
      <Skeleton key={i} width={i === lines - 1 ? '62%' : '100%'} />
    ))}
  </div>
);
