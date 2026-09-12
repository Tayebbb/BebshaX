import type { PersonaDatasetRef } from '../types/persona';

const FOOTER_KEYS = new Set(['source', 'dataset_id', 'content_hash', 'variable', 'value']);

const present = (value: unknown): boolean => value !== undefined && value !== null && value !== '';

export const formatDatasetRefValue = (value: unknown): string => {
  if (!present(value)) return 'Not recorded';
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
};

/** Dataset-variable refs carry `variable`; ML attribution refs carry `record_id`. */
export const datasetRefTitle = (ref: PersonaDatasetRef): string => {
  if (typeof ref.variable === 'string' && ref.variable.trim()) return ref.variable;
  if (typeof ref.record_id === 'string' && ref.record_id) return `Training record ${ref.record_id.slice(0, 12)}`;
  return 'Provenance';
};

/** Remaining attribution fields, flattened one level, with empty values dropped. */
export const datasetRefFields = (ref: PersonaDatasetRef): Array<[string, string]> =>
  Object.entries(ref).flatMap(([key, value]): Array<[string, string]> => {
    if (FOOTER_KEYS.has(key) || !present(value)) return [];
    if (typeof value === 'object' && !Array.isArray(value)) {
      return Object.entries(value as Record<string, unknown>)
        .filter(([, nested]) => present(nested))
        .map(([nestedKey, nested]) => [`${key}.${nestedKey}`, formatDatasetRefValue(nested)]);
    }
    return [[key, formatDatasetRefValue(value)]];
  });
