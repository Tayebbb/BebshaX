/**
 * App-wide scroll reveal: any element with the `bx-reveal` class rises in
 * when it enters the viewport (adds `bx-in`). A MutationObserver keeps
 * watching so views mounted later (tab switches, async data) animate too.
 * Call once; safe to call repeatedly.
 */
let started = false;

export function initScrollReveal(): void {
  if (started || typeof window === 'undefined' || !('IntersectionObserver' in window)) return;
  started = true;

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('bx-in');
          io.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.08, rootMargin: '0px 0px -8% 0px' }
  );

  const observeAll = (root: ParentNode) => {
    root.querySelectorAll?.('.bx-reveal:not(.bx-in)').forEach((el) => io.observe(el));
  };

  observeAll(document);

  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return;
        if (node.classList.contains('bx-reveal')) io.observe(node);
        observeAll(node);
      });
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
}
