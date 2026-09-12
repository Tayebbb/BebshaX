import { describe, expect, it } from 'vitest';
import { datasetRefFields, datasetRefTitle, formatDatasetRefValue } from '../src/utils/datasetRefs';

describe('dataset provenance refs', () => {
  it('titles dataset-variable refs by variable and shows their value', () => {
    const ref = { variable: 'segment', value: 'Budget planners', dataset_id: 'ds_1' };
    expect(datasetRefTitle(ref)).toBe('segment');
    expect(formatDatasetRefValue(ref.value)).toBe('Budget planners');
  });

  it('titles ML attribution refs by training record and lists fields without the word undefined', () => {
    const ref = {
      source: 'nvidia/Nemotron-Personas-USA',
      revision: 'abc',
      record_id: 'f00dbabe12345678',
      model_version: 'schema3',
      selection_score: 0.42,
      topic: 3,
      strategy: 'nmf',
      source_attribution: { status: 'unavailable', dataset: null, note: '' },
      source_corpus_sha256: null,
    };
    expect(datasetRefTitle(ref)).toBe('Training record f00dbabe1234');
    const fields = datasetRefFields(ref);
    const rendered = fields.map(([key, value]) => `${key}=${value}`).join('\n');
    expect(rendered).not.toMatch(/undefined|null/);
    expect(fields).toContainEqual(['record_id', 'f00dbabe12345678']);
    expect(fields).toContainEqual(['selection_score', '0.42']);
    expect(fields).toContainEqual(['source_attribution.status', 'unavailable']);
    expect(fields.some(([key]) => key === 'source')).toBe(false);
  });

  it('falls back to a generic title and formats empty values honestly', () => {
    expect(datasetRefTitle({})).toBe('Provenance');
    expect(formatDatasetRefValue(undefined)).toBe('Not recorded');
    expect(formatDatasetRefValue({ a: 1 })).toBe('{\n  "a": 1\n}');
  });
});
