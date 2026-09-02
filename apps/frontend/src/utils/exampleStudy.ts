import { Study } from '../types';

/** The "see a finished example" affordance must land on a study that is
 * actually finished. Selection is deterministic — a completed demo wins, a
 * demo parked on the report step is the fallback, and when neither exists the
 * caller renders nothing rather than sending the user into an empty shell. */
export const findExampleStudy = (studies: Study[]): Study | null => {
  const demos = studies.filter((s) => s.is_demo);
  return demos.find((s) => s.status === 'completed') ?? demos.find((s) => s.step === 5) ?? null;
};

/** Finished examples always open on the report step. */
export const EXAMPLE_STUDY_STEP = 5;
