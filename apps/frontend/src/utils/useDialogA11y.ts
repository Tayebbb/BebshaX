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

/** The re-rendered twin of a control that unmounted while a dialog was open
 * (a list that reloaded, a card that re-keyed): same id, else same tag +
 * aria-label. Focus has somewhere sensible to return to either way. */
function equivalentOf(element: HTMLElement): HTMLElement | null {
  if (element.id) return document.getElementById(element.id);
  const label = element.getAttribute('aria-label');
  if (!label || typeof CSS === 'undefined' || typeof CSS.escape !== 'function') return null;
  return document.querySelector<HTMLElement>(`${element.tagName.toLowerCase()}[aria-label="${CSS.escape(label)}"]`);
}

/**
 * Shared dialog behaviour for the app's modals (the PersonaDetailModal /
 * AuthModal protocol): on open, move focus to the first control inside the
 * dialog; while open, Escape closes it and Tab / Shift+Tab loop inside it.
 *
 * Escape stacking: the listener runs in the capture phase and consumes the
 * key with preventDefault, and every handler in the app first checks
 * `e.defaultPrevented` — so exactly one surface (the topmost) closes per press.
 * Focus is returned to the element that was focused before the dialog opened
 * — or to `returnFocusTo`, for openers that do async work (and may re-render
 * the trigger) before the dialog mounts.
 */
export function useDialogA11y(
  ref: RefObject<HTMLElement | null>,
  isOpen: boolean,
  onClose: () => void,
  opts: {
    initialFocus?: RefObject<HTMLElement | null>;
    returnFocus?: boolean;
    returnFocusTo?: RefObject<HTMLElement | null>;
    suspended?: boolean;
  } = {},
): void {
  const { initialFocus, returnFocus = true, returnFocusTo, suspended = false } = opts;
  const suspendedRef = useRef(suspended);
  suspendedRef.current = suspended;
  // Always invoke the latest onClose — callers pass fresh closures every render.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const container = ref.current;
    if (!isOpen || !container) return;
    const previouslyFocused = returnFocusTo?.current
      ?? (typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null);
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
      if (returnFocus && previouslyFocused && previouslyFocused !== document.body) {
        // Live 2026-09-14: the Start Interview dialog's opener re-rendered while
        // it was open, so Escape dropped focus on <body>.
        const target = document.contains(previouslyFocused) ? previouslyFocused : equivalentOf(previouslyFocused);
        target?.focus();
      }
    };
  }, [isOpen, ref, initialFocus, returnFocus, returnFocusTo]);
}
