import React, { useEffect, useRef } from 'react';

declare global {
  interface Window {
    VANTA?: {
      WAVES: (options: Record<string, unknown>) => { destroy: () => void };
    };
    THREE?: unknown;
  }
}

export const AnimatedBackground: React.FC = () => {
  const vantaRef = useRef<HTMLDivElement | null>(null);
  const vantaEffectRef = useRef<{ destroy: () => void } | null>(null);

  useEffect(() => {
    let checkCount = 0;
    const maxChecks = 30;

    const initVanta = () => {
      if (!vantaRef.current) return;

      if (window.VANTA && typeof window.VANTA.WAVES === 'function') {
        try {
          if (vantaEffectRef.current) {
            vantaEffectRef.current.destroy();
          }

          vantaEffectRef.current = window.VANTA.WAVES({
            el: vantaRef.current,
            mouseControls: true,
            touchControls: true,
            gyroControls: false,
            minHeight: 200.0,
            minWidth: 200.0,
            scale: 1.0,
            scaleMobile: 1.0,
            color: 0x34658e,
            shininess: 30.0,
            waveHeight: 15.0,
            waveSpeed: 1.0,
            zoom: 1.0,
          });
        } catch (e) {
          console.warn('Vanta initialization deferred:', e);
        }
      } else if (checkCount < maxChecks) {
        checkCount++;
        setTimeout(initVanta, 150);
      }
    };

    initVanta();

    return () => {
      if (vantaEffectRef.current && typeof vantaEffectRef.current.destroy === 'function') {
        vantaEffectRef.current.destroy();
        vantaEffectRef.current = null;
      }
    };
  }, []);

  return (
    <div
      ref={vantaRef}
      id="vanta-waves-bg"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        background: 'linear-gradient(180deg, #E0F2FE 0%, #BAE6FD 30%, #7DD3FC 100%)',
      }}
    />
  );
};
