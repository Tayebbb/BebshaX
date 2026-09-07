import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';
import { useDialogA11y } from '../../utils/useDialogA11y';

export interface CommandItem {
  id: string;
  label: string;
  group: string;
  icon?: React.ReactNode;
  /** Right-aligned secondary text (e.g. "Step 3 · in progress"). */
  hint?: string;
  /** Extra match terms not shown in the label. */
  keywords?: string[];
  onSelect: () => void;
}

interface CommandMenuProps {
  open: boolean;
  onClose: () => void;
  items: CommandItem[];
  placeholder?: string;
}

const matches = (item: CommandItem, q: string): boolean => {
  if (!q) return true;
  const hay = [item.label, item.group, item.hint ?? '', ...(item.keywords ?? [])].join(' ').toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => hay.includes(term));
};

/**
 * Ctrl/⌘ K jump menu. Flat keyboard model: type to filter, ↑↓ to move,
 * Enter to run, Escape to close (via the shared dialog protocol so it
 * stacks correctly above drawers and popovers).
 */
export const CommandMenu: React.FC<CommandMenuProps> = ({ open, onClose, items, placeholder = 'Search or jump to…' }) => {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  useDialogA11y(dialogRef, open, onClose, { initialFocus: inputRef });

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
  }, [open]);

  const visible = useMemo(() => items.filter((it) => matches(it, query)), [items, query]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    const row = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    row?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex]);

  if (!open) return null;

  const run = (item: CommandItem) => {
    onClose();
    item.onSelect();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => (visible.length ? (i + 1) % visible.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => (visible.length ? (i - 1 + visible.length) % visible.length : 0));
    } else if (e.key === 'Enter') {
      const item = visible[activeIndex];
      if (item) {
        e.preventDefault();
        run(item);
      }
    }
  };

  // Group headers are rendered when the group changes in filtered order.
  let lastGroup: string | null = null;

  return (
    <div className="bx-cmdk-backdrop bx-fade" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        className="bx-cmdk bx-modal"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="bx-cmdk__input-row">
          <Search size={16} aria-hidden="true" />
          <input
            ref={inputRef}
            className="bx-cmdk__input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            aria-label="Search commands and destinations"
            role="combobox"
            aria-expanded="true"
            aria-controls="bx-cmdk-list"
            aria-activedescendant={visible[activeIndex] ? `bx-cmdk-${visible[activeIndex].id}` : undefined}
            autoComplete="off"
            spellCheck={false}
          />
          <span className="bx-kbd">Esc</span>
        </div>
        <ul id="bx-cmdk-list" ref={listRef} role="listbox" className="bx-cmdk__list" aria-label="Results">
          {visible.length === 0 && <li className="bx-cmdk__empty">Nothing matches “{query}”.</li>}
          {visible.map((item, idx) => {
            const showGroup = item.group !== lastGroup;
            lastGroup = item.group;
            return (
              <React.Fragment key={item.id}>
                {showGroup && (
                  <li className="bx-cmdk__group" role="presentation">
                    {item.group}
                  </li>
                )}
                <li role="presentation">
                  <button
                    type="button"
                    id={`bx-cmdk-${item.id}`}
                    role="option"
                    aria-selected={idx === activeIndex}
                    data-index={idx}
                    className="bx-cmdk__item"
                    onMouseEnter={() => setActiveIndex(idx)}
                    onClick={() => run(item)}
                    tabIndex={-1}
                  >
                    <span className="bx-cmdk__item-icon" aria-hidden="true">
                      {item.icon}
                    </span>
                    <span className="bx-cmdk__item-text">{item.label}</span>
                    {item.hint && <span className="bx-cmdk__item-hint">{item.hint}</span>}
                  </button>
                </li>
              </React.Fragment>
            );
          })}
        </ul>
        <div className="bx-cmdk__footer">
          <span>
            <span className="bx-kbd">↑</span>
            <span className="bx-kbd">↓</span> navigate
          </span>
          <span>
            <span className="bx-kbd">
              <CornerDownLeft size={9} aria-hidden="true" />
            </span>{' '}
            open
          </span>
        </div>
      </div>
    </div>
  );
};
