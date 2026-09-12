import type { InterviewDetailResponse, CompleteInterviewResponse, SendInterviewMessageResponse } from '../types/interview';
import type { StudyReport } from '../types/study';

export const MAX_INTERVIEW_FRAME_LENGTH = 1024 * 1024;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

const isStrings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

export function decodeInterviewReply(value: unknown): SendInterviewMessageResponse {
  if (!isRecord(value) || typeof value.reply !== 'string' || !value.reply.trim() ||
      !Number.isInteger(value.turn_number) || (value.turn_number as number) < 1 ||
      typeof value.is_finished !== 'boolean') {
    throw new Error('Invalid interview reply');
  }
  for (const key of ['turn_count', 'max_turns', 'latency_ms']) {
    const field = value[key];
    if (field !== undefined && field !== null &&
        (typeof field !== 'number' || !Number.isFinite(field) || field < 0)) {
      throw new Error('Invalid interview reply');
    }
  }
  for (const key of ['suggested_questions', 'retrieved_memory_ids', 'retrieved_memories', 'drift_notes']) {
    if (value[key] !== undefined && !isStrings(value[key])) throw new Error('Invalid interview reply');
  }
  for (const key of ['served_by', 'topic', 'llm_request_id', 'contradiction_details']) {
    if (value[key] !== undefined && value[key] !== null && typeof value[key] !== 'string') {
      throw new Error('Invalid interview reply');
    }
  }
  for (const key of ['identity_drift', 'contradiction_detected']) {
    if (value[key] !== undefined && typeof value[key] !== 'boolean') throw new Error('Invalid interview reply');
  }
  if (value.topics_explored !== undefined &&
      (!isRecord(value.topics_explored) || !Object.values(value.topics_explored).every((status) => typeof status === 'string'))) {
    throw new Error('Invalid interview reply');
  }
  if (value.persona_reply !== undefined && !isRecord(value.persona_reply)) throw new Error('Invalid interview reply');
  if (isRecord(value.persona_reply)) {
    for (const key of ['retrieved_memories', 'drift_notes']) {
      if (value.persona_reply[key] !== undefined && !isStrings(value.persona_reply[key])) throw new Error('Invalid interview reply');
    }
  }
  return {
    ...value,
    topics_explored: value.topics_explored ?? {},
    suggested_questions: value.suggested_questions ?? [],
  } as unknown as SendInterviewMessageResponse;
}

export function decodeInterviewDelta(value: unknown): string {
  if (!isRecord(value) || typeof value.text !== 'string') throw new Error('Invalid interview delta');
  return value.text;
}

export function decodeInterviewFrame(payload: string): unknown {
  try {
    return JSON.parse(payload) as unknown;
  } catch {
    throw new Error('Invalid interview event JSON');
  }
}

function validInsights(value: unknown): boolean {
  return Array.isArray(value) && value.every((insight) => isRecord(insight) &&
    typeof insight.id === 'string' && typeof insight.title === 'string' && typeof insight.description === 'string' &&
    Array.isArray(insight.supporting_turn_numbers) && insight.supporting_turn_numbers.every(Number.isInteger));
}

export function decodeInterviewDetail(value: unknown, studyId: string, interviewId: string): InterviewDetailResponse {
  if (!isRecord(value) || value.id !== interviewId || value.study_id !== studyId ||
      typeof value.persona_id !== 'string' || !value.persona_id || typeof value.status !== 'string' ||
      !['active', 'completed', 'failed', 'paused'].includes(value.status) ||
      !Array.isArray(value.turns) || !value.turns.every((turn) => isRecord(turn) &&
        typeof turn.id === 'string' && typeof turn.content === 'string' && Number.isInteger(turn.turn_number) &&
        typeof turn.role === 'string' && ['interviewer', 'persona', 'system', 'researcher', 'user', 'assistant'].includes(turn.role)) ||
      !validInsights(value.structured_insights ?? []) ||
      (value.suggested_questions !== undefined && !isStrings(value.suggested_questions))) {
    throw new Error('Invalid interview detail response');
  }
  return { ...value, structured_insights: value.structured_insights ?? [], suggested_questions: value.suggested_questions ?? [] } as unknown as InterviewDetailResponse;
}

export function decodeInterviewSynthesis(value: unknown): CompleteInterviewResponse {
  if (!isRecord(value) || (value.status !== undefined && value.status !== 'completed') ||
      (value.key_findings !== undefined && !isStrings(value.key_findings)) ||
      !validInsights(value.structured_insights ?? []) ||
      (value.source !== undefined && value.source !== 'llm' && value.source !== 'unavailable') ||
      (value.error_code != null && typeof value.error_code !== 'string') ||
      (value.served_by != null && typeof value.served_by !== 'string') ||
      (value.insights_dropped !== undefined &&
        (!Number.isInteger(value.insights_dropped) || (value.insights_dropped as number) < 0))) {
    throw new Error('Invalid interview synthesis response');
  }
  const written = typeof value.summary === 'string' && value.summary.trim().length > 0;
  // The interview closes even when no route could write the analysis; that
  // outcome is only honest when the server says so explicitly.
  const closedWithoutSynthesis = value.summary == null && value.source === 'unavailable';
  if (!written && !closedWithoutSynthesis) throw new Error('Invalid interview synthesis response');
  return { ...value, summary: written ? (value.summary as string) : null } as unknown as CompleteInterviewResponse;
}

export function decodeStudyReport(value: unknown): StudyReport {
  if (!isRecord(value) || typeof value.executive_summary !== 'string' ||
      !isStrings(value.key_findings) || !isStrings(value.recommendations) ||
      (value.limitations != null && typeof value.limitations !== 'string') ||
      (value.version != null && (!Number.isInteger(value.version) || (value.version as number) < 1))) {
    throw new Error('Invalid saved report response');
  }
  return value as unknown as StudyReport;
}