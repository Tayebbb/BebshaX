import React from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Square icon-only button; pass `aria-label`. */
  icon?: boolean;
  block?: boolean;
  /** Shows a spinner and disables the control while true. */
  loading?: boolean;
  leadingIcon?: React.ReactNode;
  trailingIcon?: React.ReactNode;
}

/** The one button. Variants are intents, not colours. */
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    icon = false,
    block = false,
    loading = false,
    leadingIcon,
    trailingIcon,
    className,
    children,
    disabled,
    type = 'button',
    ...rest
  },
  ref,
) {
  const classes = [
    'bx-btn',
    `bx-btn--${variant}`,
    size !== 'md' ? `bx-btn--${size}` : '',
    icon ? 'bx-btn--icon' : '',
    block ? 'bx-btn--block' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button ref={ref} type={type} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Spinner /> : leadingIcon}
      {children}
      {!loading && trailingIcon}
    </button>
  );
});

const Spinner: React.FC = () => (
  <span
    aria-hidden="true"
    style={{
      width: 14,
      height: 14,
      borderRadius: '50%',
      border: '2px solid currentColor',
      borderRightColor: 'transparent',
      animation: 'bx-spin 0.7s linear infinite',
      flexShrink: 0,
    }}
  />
);
