import React from 'react';
import { ProvenanceClass } from '../types';

interface StatusBadgeProps {
  type: 'provenance' | 'status' | 'pool' | 'failure';
  value: string | ProvenanceClass;
  detail?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ type, value, detail }) => {
  if (type === 'provenance') {
    const provClass = value as ProvenanceClass;
    let badgeClass = 'badge-synthetic';
    let icon = '⚡';
    if (provClass === 'OBSERVED') {
      badgeClass = 'badge-observed';
      icon = '🔍';
    } else if (provClass === 'INFERRED') {
      badgeClass = 'badge-inferred';
      icon = '🧠';
    }

    return (
      <span className={`badge ${badgeClass}`} title={detail || `${provClass} Provenance`}>
        <span>{icon}</span> {provClass}
      </span>
    );
  }

  if (type === 'status') {
    const isSuccess = value === 'success' || value === 'healthy' || value === 'true';
    return (
      <span className={`badge ${isSuccess ? 'badge-success' : 'badge-fail'}`}>
        <span>{isSuccess ? '●' : '✕'}</span> {value}
      </span>
    );
  }

  if (type === 'pool') {
    return (
      <span className="badge badge-pool">
        <span>⚙</span> {value}
      </span>
    );
  }

  return (
    <span className="badge badge-fail" title={detail}>
      <span>⚠</span> {value}
    </span>
  );
};
