import { describe, expect, it } from 'vitest';
import { formatScorePercent } from '../src/components/dashboard/views/workflow/Step5Report';

describe('Report score formatting', () => {
  it.each([
    [0.85, '85%'], [1, '100%'], [0, '0%'], [0.004, '0%'],
    [85, '85%'], [100, '100%'], [42.6, '43%'],
  ])('renders %p as %s whether the model reported a fraction or a percent', (value, expected) => {
    expect(formatScorePercent(value)).toBe(expected);
  });

  it.each([null, undefined, -1, 101, Number.NaN, Number.POSITIVE_INFINITY, '85', {}])(
    'renders %p as an em dash instead of a fabricated number', (value) => {
      expect(formatScorePercent(value)).toBe('—');
    },
  );
});
