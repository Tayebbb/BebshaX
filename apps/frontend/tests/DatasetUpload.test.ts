import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/services/api';
import { datasetUploadProblem, MAX_DATASET_UPLOAD_BYTES } from '../src/utils/datasetUpload';

const fetchMock = vi.fn<typeof fetch>();

describe('Dataset upload transport', () => {
  let previousMockMode: boolean;

  beforeEach(() => {
    previousMockMode = api.isMockMode();
    api.setMockMode(false);
    localStorage.clear();
    sessionStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    api.setAuthToken('upload-fixture-token');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    api.setMockMode(previousMockMode);
    localStorage.clear();
    sessionStorage.clear();
  });

  it('lets the browser write the multipart boundary instead of forcing a JSON content type', async () => {
    const created = { id: 'ds_1', study_id: 'study_1', name: 'Survey', row_count: 24, column_count: 5 };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(created), { status: 201 }));
    const form = new FormData();
    form.append('file', new File(['age,budget\n19,4500\n'], 'survey.csv', { type: 'text/csv' }));
    form.append('name', 'Survey');

    await expect(api.uploadDataset(form, 'study_1')).resolves.toEqual(created);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/studies\/study_1\/datasets\/upload$/);
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(form);
    const headers = init?.headers as Record<string, string>;
    // A forced application/json header made the backend's multipart guard answer 422.
    expect(Object.keys(headers).map((name) => name.toLowerCase())).not.toContain('content-type');
    expect(headers.Authorization).toBe('Bearer upload-fixture-token');
  });

  it('surfaces the backend envelope for a rejected upload', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      detail: 'Uploaded file exceeds the 25 MB limit.', error_code: 'payload_too_large', request_id: 'req_413',
    }), { status: 413 }));
    const form = new FormData();
    form.append('file', new File(['x'], 'big.csv'));
    form.append('name', 'Big');
    await expect(api.uploadDataset(form, 'study_1')).rejects.toMatchObject({
      status: 413, message: 'Uploaded file exceeds the 25 MB limit.', requestId: 'req_413',
    });
  });

  it('rejects unusable picks before any request is made', () => {
    expect(datasetUploadProblem(null)).toMatch(/Choose a CSV or JSON/);
    expect(datasetUploadProblem(new File(['a'], 'notes.txt'))).toMatch(/Only \.csv and \.json/);
    expect(datasetUploadProblem(new File([], 'empty.csv'))).toMatch(/empty/);
    const oversized = new File([new Uint8Array(1)], 'huge.json');
    Object.defineProperty(oversized, 'size', { value: MAX_DATASET_UPLOAD_BYTES + 1 });
    expect(datasetUploadProblem(oversized)).toMatch(/limit is 25 MB/);
    expect(datasetUploadProblem(new File(['{}'], 'records.JSON'))).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
