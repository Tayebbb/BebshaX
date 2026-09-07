import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Shared dialog behaviour for the app's modals (the PersonaDetailModal /
 * AuthModal protocol): on open, move focus to the first control inside the
 * dialog; while open, Escape closes it and Tab / Shift+Tab loop inside it.
 *
 * Escape stacking: the listener runs in the capture phase and consumes the
 * key with preventDefault, and every handler in the app first checks
 * `e.defaultPrevented` — so exactly one surface (the topmost) closes per press.
 * Focus is returned to the element that was focused before the dialog opened.
 */
export function useDialogA11y(
  ref: RefObject<HTMLElement | null>,
  isOpen: boolean,
  onClose: () => void,
  opts: { initialFocus?: RefObject<HTMLElement | null>; returnFocus?: boolean } = {},
): void {
  const { initialFocus, returnFocus = true } = opts;
  // Always invoke the latest onClose — callers pass fresh closures every render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null;

    const focusables = (): HTMLElement[] =>
      Array.from(ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
        (el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true',
      );

    // Defer one frame: the dialog's children may mount in the same commit.
    const focusTimer = setTimeout(() => {
      const target = initialFocus?.current ?? focusables()[0];
      target?.focus();
    }, 0);

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key === 'Tab') {
        const els = focusables();
        if (els.length === 0) return;
        const first = els[0];
        const last = els[els.length - 1];
        const active = document.activeElement as HTMLElement | null;
        const inside = !!active && !!ref.current?.contains(active);
        if (e.shiftKey && (!inside || active === first)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (!inside || active === last)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      clearTimeout(focusTimer);
      document.removeEventListener('keydown', onKeyDown, true);
      if (returnFocus && previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [isOpen, ref, initialFocus, returnFocus]);
}
