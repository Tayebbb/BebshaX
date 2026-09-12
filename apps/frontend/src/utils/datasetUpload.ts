/** Mirrors the backend ceiling (datasets/security.py) so an oversized pick fails before the upload starts. */
export const MAX_DATASET_UPLOAD_BYTES = 25 * 1024 * 1024;
export const DATASET_FILE_PATTERN = /\.(csv|json)$/i;

export const datasetUploadProblem = (file: File | null): string | null => {
  if (!file) return 'Choose a CSV or JSON file first.';
  if (!DATASET_FILE_PATTERN.test(file.name)) return 'Only .csv and .json files can be profiled.';
  if (file.size === 0) return 'That file is empty.';
  if (file.size > MAX_DATASET_UPLOAD_BYTES) return `That file is ${(file.size / (1024 * 1024)).toFixed(1)} MB; the limit is 25 MB.`;
  return null;
};
