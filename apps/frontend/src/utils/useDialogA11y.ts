import { useEffect, useRef, type RefObject } from 'react';

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

function isFocusable(element: HTMLElement): boolean {
  if (element.tabIndex < 0 && !element.hasAttribute('tabindex')) return false;
  if (element.matches(':disabled, input[type="hidden"]')) return false;
  if (element.closest('[hidden], [inert], [aria-hidden="true"]')) return false;

  for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement) {
    const style = getComputedStyle(ancestor);
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') {
      return false;
    }
  }
  return true;
}

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
  opts: { initialFocus?: RefObject<HTMLElement | null>; returnFocus?: boolean; suspended?: boolean } = {},
): void {
  const { initialFocus, returnFocus = true, suspended = false } = opts;
  const suspendedRef = useRef(suspended);
  suspendedRef.current = suspended;
  // Always invoke the latest onClose — callers pass fresh closures every render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const container = ref.current;
    if (!isOpen || !container) return;
    const previouslyFocused = typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null;
    const addedTabIndex = !container.hasAttribute('tabindex');
    if (addedTabIndex) container.setAttribute('tabindex', '-1');

    const focusables = (): HTMLElement[] =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE))
        .filter((element) => element.tabIndex >= 0 && isFocusable(element));

    const focusInside = () => {
      if (suspendedRef.current || !container.isConnected) return;
      const preferred = initialFocus?.current;
      const target = preferred && container.contains(preferred) && isFocusable(preferred)
        ? preferred
        : focusables()[0] ?? container;
      target.focus();
    };

    const recoverFocus = () => {
      if (suspendedRef.current) return;
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !container.contains(active) || !isFocusable(active)) {
        focusInside();
      }
    };

    // Defer one frame: the dialog's children may mount in the same commit.
    const focusTimer = setTimeout(focusInside, 0);
    const observer = new MutationObserver(recoverFocus);
    observer.observe(container, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['disabled', 'hidden', 'inert', 'aria-hidden', 'tabindex', 'style', 'class'],
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || suspendedRef.current) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === 'Tab') {
        const elements = focusables();
        if (elements.length === 0) {
          event.preventDefault();
          focusInside();
          return;
        }
        const first = elements[0];
        const last = elements[elements.length - 1];
        const active = document.activeElement as HTMLElement | null;
        const inTabOrder = !!active && elements.includes(active);
        if (event.shiftKey && (!inTabOrder || active === first)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (!inTabOrder || active === last)) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      clearTimeout(focusTimer);
      observer.disconnect();
      document.removeEventListener('keydown', onKeyDown, true);
      if (addedTabIndex && container.getAttribute('tabindex') === '-1') container.removeAttribute('tabindex');
      if (returnFocus && previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [isOpen, ref, initialFocus, returnFocus]);
}
