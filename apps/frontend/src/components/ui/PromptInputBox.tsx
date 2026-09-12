import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Paperclip, Square, X } from 'lucide-react';
import './promptinputbox.css';

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export interface PromptInputBoxProps {
  value: string;
  onValueChange: (value: string) => void;
  onSend: (message: string, files: File[]) => void;
  /** Called when the stop button is pressed while `isLoading`. Without it the button is disabled. */
  onStop?: () => void;
  isLoading?: boolean;
  disabled?: boolean;
  /** Shown as the send button's title while `disabled` (explains why). */
  disabledReason?: string;
  placeholder?: string;
  /** Enables the paperclip, drag-drop and paste of a single image. */
  allowAttachments?: boolean;
  /** Rendered on the left of the action row (mode chips, counters…). */
  leftActions?: React.ReactNode;
  /** Small mono footer under the box (turn counter, hints). */
  footer?: React.ReactNode;
  maxHeight?: number;
  textareaRef?: React.Ref<HTMLTextAreaElement>;
  'aria-label'?: string;
  sendLabel?: string;
  className?: string;
}

const isImage = (f: File) => f.type.startsWith('image/');

export const PromptInputBox: React.FC<PromptInputBoxProps> = ({
  value,
  onValueChange,
  onSend,
  onStop,
  isLoading = false,
  disabled = false,
  disabledReason,
  placeholder = 'Type your message…',
  allowAttachments = false,
  leftActions,
  footer,
  maxHeight = 200,
  textareaRef,
  'aria-label': ariaLabel = 'Message',
  sendLabel = 'Send message',
  className,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState(false);
  const [dragging, setDragging] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const innerRef = useRef<HTMLTextAreaElement | null>(null);
  const composingRef = useRef(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const setRefs = (el: HTMLTextAreaElement | null) => {
    innerRef.current = el;
    if (typeof textareaRef === 'function') textareaRef(el);
    else if (textareaRef) (textareaRef as React.MutableRefObject<HTMLTextAreaElement | null>).current = el;
  };

  useEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, [value, maxHeight]);

  useEffect(() => {
    if (!preview) return;
    return () => URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    const d = dialogRef.current;
    if (!d || typeof d.showModal !== 'function') return;
    if (lightbox && !d.open) d.showModal();
    else if (!lightbox && d.open) d.close();
  }, [lightbox]);

  const acceptFile = useCallback(
    (f: File) => {
      if (!allowAttachments || !isImage(f) || f.size > MAX_IMAGE_BYTES) return;
      setFile(f);
      setPreview(URL.createObjectURL(f));
    },
    [allowAttachments],
  );

  const clearFile = () => {
    setFile(null);
    setPreview(null);
  };

  useEffect(() => {
    if (!allowAttachments) return;
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.type.startsWith('image/'));
      const f = item?.getAsFile();
      if (f) {
        e.preventDefault();
        acceptFile(f);
      }
    };
    document.addEventListener('paste', onPaste);
    return () => document.removeEventListener('paste', onPaste);
  }, [allowAttachments, acceptFile]);

  const hasContent = value.trim() !== '' || file !== null;
  const canSend = hasContent && !isLoading && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSend(value, file ? [file] : []);
    clearFile();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (composingRef.current || event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const dragProps = allowAttachments
    ? {
        onDragOver: (e: React.DragEvent) => {
          e.preventDefault();
          setDragging(true);
        },
        onDragLeave: (e: React.DragEvent) => {
          e.preventDefault();
          setDragging(false);
        },
        onDrop: (e: React.DragEvent) => {
          e.preventDefault();
          setDragging(false);
          const f = Array.from(e.dataTransfer.files).find(isImage);
          if (f) acceptFile(f);
        },
      }
    : {};

  const primaryLabel = isLoading ? (onStop ? 'Stop generation' : 'Waiting for reply') : sendLabel;

  return (
    <div className={['bx-prompt-wrap', className].filter(Boolean).join(' ')}>
      <div
        className={[
          'bx-prompt',
          isLoading ? 'bx-prompt--loading' : '',
          dragging ? 'bx-prompt--dragging' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        {...dragProps}
      >
        {file && preview && (
          <div className="bx-prompt-files">
            <button
              type="button"
              className="bx-prompt-thumb"
              onClick={() => setLightbox(true)}
              aria-label={`Preview ${file.name}`}
            >
              <img src={preview} alt={file.name} />
            </button>
            <button
              type="button"
              className="bx-prompt-thumb-remove"
              onClick={clearFile}
              aria-label={`Remove ${file.name}`}
            >
              <X size={11} aria-hidden="true" />
            </button>
          </div>
        )}

        <textarea
          ref={setRefs}
          className="bx-prompt-input"
          rows={1}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => { composingRef.current = true; }}
          onCompositionEnd={() => { composingRef.current = false; }}
          placeholder={placeholder}
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
          aria-label={ariaLabel}
        />

        <div className="bx-prompt-actions">
          <div className="bx-prompt-actions-left">
            {allowAttachments && (
              <span className="bx-tip" data-tip="Attach image">
                <button
                  type="button"
                  className="bx-prompt-icon-btn"
                  onClick={() => uploadRef.current?.click()}
                  disabled={disabled}
                  aria-label="Attach image"
                >
                  <Paperclip size={17} aria-hidden="true" />
                </button>
                <input
                  ref={uploadRef}
                  type="file"
                  accept="image/*"
                  className="bx-prompt-file-input"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) acceptFile(f);
                    e.target.value = '';
                  }}
                />
              </span>
            )}
            {leftActions}
          </div>

          <span className="bx-tip" data-tip={primaryLabel}>
            <button
              type="button"
              className={['bx-prompt-send', canSend ? 'bx-prompt-send--ready' : ''].filter(Boolean).join(' ')}
              onClick={isLoading ? onStop : submit}
              disabled={isLoading ? !onStop : !canSend}
              title={disabled ? disabledReason : undefined}
              aria-label={primaryLabel}
            >
              {isLoading ? (
                <Square size={13} className="bx-prompt-stop-icon" aria-hidden="true" />
              ) : (
                <ArrowUp size={17} strokeWidth={2.5} aria-hidden="true" />
              )}
            </button>
          </span>
        </div>
      </div>

      {footer && <div className="bx-prompt-footer">{footer}</div>}

      {allowAttachments && (
        <dialog
          ref={dialogRef}
          className="bx-prompt-lightbox"
          onClose={() => setLightbox(false)}
          onClick={(e) => {
            if (e.target === e.currentTarget) setLightbox(false);
          }}
          aria-label="Image preview"
        >
          {preview && <img src={preview} alt={file?.name ?? 'Attachment preview'} />}
          <button
            type="button"
            className="bx-prompt-lightbox-close"
            onClick={() => setLightbox(false)}
            aria-label="Close preview"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </dialog>
      )}
    </div>
  );
};
