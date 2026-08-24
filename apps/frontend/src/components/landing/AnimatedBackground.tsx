import React, { useEffect, useRef } from 'react';

declare global {
  interface Window {
    VANTA?: {
      TOPOLOGY: (options: Record<string, unknown>) => {
        destroy: () => void;
        onMouseMove?: (e: { clientX: number; clientY: number }) => void;
        p5?: { loop?: () => void; redraw?: () => void };
      };
      WAVES?: (options: Record<string, unknown>) => { destroy: () => void };
    };
    p5?: unknown;
  }
}

export const AnimatedBackground: React.FC = () => {
  const vantaRef = useRef<HTMLDivElement | null>(null);
  const vantaEffectRef = useRef<{
    destroy: () => void;
    onMouseMove?: (e: { clientX: number; clientY: number }) => void;
    p5?: { loop?: () => void; redraw?: () => void };
  } | null>(null);

  useEffect(() => {
    let checkCount = 0;
    const maxChecks = 30;
    let animFrameId: number | null = null;
    let time = 0;
    let userMouseX = typeof window !== 'undefined' ? window.innerWidth / 2 : 500;
    let userMouseY = typeof window !== 'undefined' ? window.innerHeight / 2 : 400;
    let hasUserMoved = false;
    let isVisible = true;
    let isIntersecting = true;

    const prefersReducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const handleWindowMouseMove = (e: MouseEvent) => {
      userMouseX = e.clientX;
      userMouseY = e.clientY;
      hasUserMoved = true;
    };

    window.addEventListener('mousemove', handleWindowMouseMove, { passive: true });

    const stopMotionLoop = () => {
      if (animFrameId !== null) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
      }
    };

    const startMotionLoop = () => {
      if (prefersReducedMotion || !isVisible || !isIntersecting || animFrameId !== null) {
        return;
      }

      const step = () => {
        time += 0.02;

        if (vantaEffectRef.current) {
          const effect = vantaEffectRef.current;

          // Compute smooth organic Lissajous curves so the mesh never stops evolving
          const winW = window.innerWidth || 1200;
          const winH = window.innerHeight || 800;

          const waveX = (Math.sin(time * 0.75) * 0.45 + 0.5) * winW;
          const waveY = (Math.cos(time * 0.55) * 0.45 + 0.5) * winH;

          // Harmoniously blend ambient organic drift with user mouse position
          const targetX = hasUserMoved ? userMouseX * 0.65 + waveX * 0.35 : waveX;
          const targetY = hasUserMoved ? userMouseY * 0.65 + waveY * 0.35 : waveY;

          if (typeof effect.onMouseMove === 'function') {
            try {
              effect.onMouseMove({ clientX: targetX, clientY: targetY });
            } catch {
              // Ignore if internal canvas is busy
            }
          }
        }

        animFrameId = requestAnimationFrame(step);
      };

      animFrameId = requestAnimationFrame(step);
    };

    // Pause animation when tab is inactive or hidden
    const handleVisibilityChange = () => {
      isVisible = !document.hidden;
      if (isVisible && isIntersecting) {
        if (vantaEffectRef.current?.p5?.loop) {
          try { vantaEffectRef.current.p5.loop(); } catch {}
        }
        startMotionLoop();
      } else {
        stopMotionLoop();
        if (vantaEffectRef.current?.p5?.redraw) {
          // keep static frame
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Pause animation when hero background is scrolled out of viewport
    let observer: IntersectionObserver | null = null;
    if (typeof IntersectionObserver !== 'undefined' && vantaRef.current) {
      observer = new IntersectionObserver(
        ([entry]) => {
          isIntersecting = entry.isIntersecting;
          if (isIntersecting && isVisible) {
            startMotionLoop();
          } else {
            stopMotionLoop();
          }
        },
        { threshold: 0.05 }
      );
      observer.observe(vantaRef.current);
    }

    const initVanta = () => {
      if (!vantaRef.current) return;

      if (window.VANTA && typeof window.VANTA.TOPOLOGY === 'function') {
        try {
          if (vantaEffectRef.current) {
            vantaEffectRef.current.destroy();
          }

          vantaEffectRef.current = window.VANTA.TOPOLOGY({
            el: vantaRef.current,
            mouseControls: !prefersReducedMotion,
            touchControls: !prefersReducedMotion,
            gyroControls: false,
            minHeight: 200.0,
            minWidth: 200.0,
            scale: 1.0,
            scaleMobile: 1.0,
            color: 0xf6c878,
            backgroundColor: 0x080909,
          });

          // Ensure p5 rendering loop stays unpaused
          if (!prefersReducedMotion && vantaEffectRef.current?.p5?.loop) {
            vantaEffectRef.current.p5.loop();
          }

          startMotionLoop();
        } catch (e) {
          console.warn('Vanta Topology initialization deferred:', e);
        }
      } else if (checkCount < maxChecks) {
        checkCount++;
        setTimeout(initVanta, 150);
      }
    };

    initVanta();

    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (observer) {
        observer.disconnect();
      }
      stopMotionLoop();
      if (vantaEffectRef.current && typeof vantaEffectRef.current.destroy === 'function') {
        vantaEffectRef.current.destroy();
        vantaEffectRef.current = null;
      }
    };
  }, []);

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '100vh',
        minHeight: '760px',
        maxHeight: '1080px',
        zIndex: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
        background: '#080909',
      }}
    >
      {/* Vanta Topology Canvas */}
      <div
        ref={vantaRef}
        id="vanta-topology-bg"
        style={{
          width: '100%',
          height: '100%',
          opacity: 0.92,
        }}
      />

      {/* Smooth bottom transition fade to solid #080909 */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '240px',
          background: 'linear-gradient(to bottom, rgba(8, 9, 9, 0) 0%, rgba(8, 9, 9, 0.7) 60%, #080909 100%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
