import { describe, it, expect } from 'vitest';
import { api } from '../src/services/api';

describe('Frontend API Service with Mock Fallback', () => {
  it('returns health check status', async () => {
    const health = await api.getHealth();
    expect(health).toHaveProperty('status');
    expect(health).toHaveProperty('version');
  });

  it('retrieves provenance records and routes status', async () => {
    const prov = await api.getProvenance(10);
    expect(prov.items.length).toBeGreaterThan(0);
    expect(prov.items[0]).toHaveProperty('request_id');
    expect(prov.items[0]).toHaveProperty('task');

    const status = await api.getRoutesStatus();
    expect(status.providers.length).toBeGreaterThan(0);
    expect(status.pools.length).toBeGreaterThan(0);
  });

  it('generates a synthetic persona with full provenance', async () => {
    const result = await api.generatePersona(
      'biz_fintech_01',
      'Test Variable Courier',
      ['Fast turnaround', 'High sensitivity']
    );
    expect(result.persona).toHaveProperty('id');
    expect(result.persona.attributes.length).toBeGreaterThan(0);
    expect(result.provenance.success).toBe(true);
  });

  it('sends interactive interview message and receives grounded response', async () => {
    const conv = await api.startConversation('per_sarah_01', 'Test Interview');
    expect(conv.id).toBeDefined();

    const turnResult = await api.sendMessage(conv.id, 'How do you handle unexpected expenses?');
    expect(turnResult.userTurn.content).toBe('How do you handle unexpected expenses?');
    expect(turnResult.assistantTurn.role).toBe('assistant');
    expect(turnResult.assistantTurn.content.length).toBeGreaterThan(10);
  });
});
