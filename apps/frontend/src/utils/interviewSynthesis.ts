import type { Interview, InterviewSynthesisMetadata } from '../types/interview';

/** True when the interview is closed but no model route could write its analysis. */
export const synthesisUnavailable = (
  interview: Pick<Interview, 'status' | 'summary' | 'configuration'> | null | undefined,
): boolean => {
  if (!interview || interview.status !== 'completed' || (interview.summary ?? '').trim()) return false;
  const synthesis = interview.configuration?.synthesis as InterviewSynthesisMetadata | undefined;
  return synthesis?.source === 'unavailable';
};
