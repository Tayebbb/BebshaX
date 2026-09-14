import React, { useRef } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import '../dashboard/views/studies.css';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  /** Destructive actions render the confirm button in the danger variant. */
  destructive?: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation with initial focus on Cancel; Escape/outside clicks are
 * ignored while the confirmed action is in flight. */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open, title, description, confirmLabel, destructive = false, busy = false, error = null, onConfirm, onCancel,
}) => {
  const cancelRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next && !busy) onCancel(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="sd-dialog-overlay" />
        <Dialog.Content
          className="sd-dialog"
          aria-modal="true"
          onOpenAutoFocus={(event) => { event.preventDefault(); cancelRef.current?.focus(); }}
          onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}
          onInteractOutside={(event) => { if (busy) event.preventDefault(); }}
        >
          <Dialog.Title className="sd-dialog-title">{title}</Dialog.Title>
          <Dialog.Description className="sd-dialog-description">{description}</Dialog.Description>
          {error && (
            <p className="sd-delete-error" role="alert">
              <AlertCircle size={17} aria-hidden="true" />
              <span>{error}</span>
            </p>
          )}
          <div className="sd-dialog-actions">
            <Button ref={cancelRef} onClick={onCancel} disabled={busy}>Cancel</Button>
            <Button variant={destructive ? 'danger' : 'primary'} loading={busy} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
