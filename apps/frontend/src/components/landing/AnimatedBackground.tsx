import React, { useEffect, useRef } from 'react';

/**
 * Evidence Constellation — the living environment of the hero fold.
 *
 * Concept: BebshaX turns scattered evidence into grounded synthetic minds.
 * The background is a drifting field of evidence nodes; nearby nodes link
 * into constellations, and a handful of "grounded" nodes pulse gold — the
 * moments evidence becomes a persona. The cursor is gravity: the field
 * leans gently toward presence without ever chasing it.
 *
 * Engineering: in-house canvas (replaces the p5/VANTA CDN payload).
 * ~70 nodes, O(n²) link pass (trivial at this count), 30 fps frame gate,
 * devicePixelRatio clamped, paused when offscreen or the tab hides,
 * reduced-motion renders one static frame. Zero dependencies.
 */

const GOLD = '246, 200, 120';
const LINK_DIST = 150;
const FPS_INTERVAL = 1000 / 30;

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  grounded: boolean; // pulses gold
  phase: number;
}

export const AnimatedBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    if (typeof ResizeObserver === 'undefined' || typeof IntersectionObserver === 'undefined') {
      return; // jsdom / ancient browsers: static gradient background only
    }
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let nodes: Node[] = [];
    let raf: number | null = null;
    let last = 0;
    let visible = !document.hidden;
    let intersecting = true;
    // cursor gravity, lerped so the field settles with inertia
    let mx = -9999;
    let my = -9999;
    let smx = -9999;
    let smy = -9999;

    const seed = () => {
      const count = Math.min(80, Math.max(40, Math.round((width * height) / 26000)));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r: 1 + Math.random() * 1.6,
        grounded: Math.random() < 0.12,
        phase: Math.random() * Math.PI * 2,
      }));
    };

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      dpr = Math.min(window.devicePixelRatio || 1, 1.75);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (nodes.length === 0) seed();
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height);

      // cursor inertia
      smx += (mx - smx) * 0.06;
      smy += (my - smy) * 0.06;

      // links first (under the nodes)
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK_DIST * LINK_DIST) {
            const alpha = (1 - Math.sqrt(d2) / LINK_DIST) * 0.14;
            ctx.strokeStyle = `rgba(${GOLD}, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (const n of nodes) {
        // gentle drift + soft cursor gravity
        const dx = smx - n.x;
        const dy = smy - n.y;
        const d2 = dx * dx + dy * dy;
        if (d2 > 1 && d2 < 240 * 240) {
          const f = 0.012 / Math.sqrt(d2);
          n.vx += dx * f;
          n.vy += dy * f;
        }
        // friction keeps velocities physical
        n.vx *= 0.985;
        n.vy *= 0.985;
        n.x += n.vx;
        n.y += n.vy;
        // wrap around edges
        if (n.x < -20) n.x = width + 20;
        if (n.x > width + 20) n.x = -20;
        if (n.y < -20) n.y = height + 20;
        if (n.y > height + 20) n.y = -20;

        const pulse = n.grounded ? 0.5 + 0.5 * Math.sin(t / 900 + n.phase) : 0;
        const alpha = n.grounded ? 0.35 + pulse * 0.45 : 0.3;
        const radius = n.grounded ? n.r + pulse * 1.4 : n.r;
        ctx.fillStyle = `rgba(${GOLD}, ${alpha})`;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fill();
        if (n.grounded && pulse > 0.15) {
          ctx.fillStyle = `rgba(${GOLD}, ${pulse * 0.08})`;
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius * 4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    const loop = (t: number) => {
      raf = requestAnimationFrame(loop);
      if (t - last < FPS_INTERVAL) return; // 30fps gate
      last = t;
      draw(t);
    };

    const start = () => {
      if (reduced || raf !== null || !visible || !intersecting) return;
      raf = requestAnimationFrame(loop);
    };
    const stop = () => {
      if (raf !== null) {
        cancelAnimationFrame(raf);
        raf = null;
      }
    };

    const onMouse = (e: MouseEvent) => {
      mx = e.clientX;
      const rect = wrap.getBoundingClientRect();
      my = e.clientY - rect.top;
    };
    const onVisibility = () => {
      visible = !document.hidden;
      visible && intersecting ? start() : stop();
    };

    const ro = new ResizeObserver(() => {
      resize();
      if (reduced) draw(0);
    });
    ro.observe(wrap);
    resize();

    const io = new IntersectionObserver(
      ([entry]) => {
        intersecting = entry.isIntersecting;
        intersecting && visible ? start() : stop();
      },
      { threshold: 0.02 }
    );
    io.observe(wrap);

    window.addEventListener('mousemove', onMouse, { passive: true });
    document.addEventListener('visibilitychange', onVisibility);

    if (reduced) {
      draw(0); // one static constellation, no loop
    } else {
      start();
    }

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      window.removeEventListener('mousemove', onMouse);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
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
        background:
          'radial-gradient(1100px 600px at 50% -10%, rgba(246, 200, 120, 0.06), transparent 60%), #080909',
      }}
    >
      <canvas ref={canvasRef} style={{ display: 'block' }} />

      {/* bottom transition into the solid page surface */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '240px',
          background:
            'linear-gradient(to bottom, rgba(8, 9, 9, 0) 0%, rgba(8, 9, 9, 0.7) 60%, #080909 100%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
