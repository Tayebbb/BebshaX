import { Component, ErrorInfo, ReactNode } from 'react';
import { RequestIdTag } from './RequestIdTag';
import { fromUnknownError } from '../../utils/apiError';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  children: ReactNode;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary] Render error caught:', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    const details = fromUnknownError(this.state.error);

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh',
          backgroundColor: 'var(--bg-pure)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
        }}
      >
        <div
          style={{
            textAlign: 'center',
            maxWidth: '480px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '16px',
            padding: '40px 32px',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <div style={{ fontSize: '2.5rem', marginBottom: '16px' }}>⚠️</div>
          <h1
            style={{
              fontSize: '1.35rem',
              fontWeight: 700,
              color: 'var(--text-main)',
              marginBottom: '10px',
            }}
          >
            Something went wrong
          </h1>
          <p
            style={{
              fontSize: '0.9rem',
              color: 'var(--text-secondary)',
              marginBottom: '24px',
              lineHeight: 1.5,
            }}
          >
            An unexpected error occurred. Reloading the page usually fixes it.
          </p>
          {details.message && (
            <pre
              style={{
                textAlign: 'left',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontSize: '0.74rem',
                color: 'var(--text-muted)',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '10px 12px',
                marginBottom: '16px',
                maxHeight: '140px',
                overflow: 'auto',
                fontFamily: 'var(--font-mono, monospace)',
              }}
            >
              {details.errorCode ? `${details.errorCode}: ` : ''}
              {details.message}
            </pre>
          )}
          {details.requestId && (
            <div style={{ marginBottom: '16px' }}>
              <RequestIdTag requestId={details.requestId} />
            </div>
          )}
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              background: 'var(--accent-gradient)',
              border: 'none',
              borderRadius: '10px',
              padding: '10px 24px',
              color: 'var(--text-on-accent)',
              fontWeight: 700,
              fontSize: '0.9rem',
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
