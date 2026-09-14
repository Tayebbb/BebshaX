/** Copy text to the clipboard, falling back to a selection-based copy when the
 * async Clipboard API is unavailable or refused (background tabs, insecure
 * contexts, permission denied). Resolves to whether anything was copied. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the selection path
  }
  if (typeof document === 'undefined') return false;
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.setAttribute('aria-hidden', 'true');
  area.style.position = 'fixed';
  area.style.top = '-1000px';
  area.style.opacity = '0';
  document.body.appendChild(area);
  const active = document.activeElement as HTMLElement | null;
  try {
    area.focus();
    area.select();
    area.setSelectionRange(0, text.length);
    return typeof document.execCommand === 'function' && document.execCommand('copy');
  } catch {
    return false;
  } finally {
    area.remove();
    active?.focus?.();
  }
}
