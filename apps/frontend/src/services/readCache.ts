interface Cached<Value> { value: Value; expires: number; size: number; }

export class BoundedReadCache<Value> {
  private values = new Map<string, Cached<Value>>();
  private pending = new Map<string, Promise<Value>>();
  private generation = 0;
  private size = 0;

  constructor(private readonly maxEntries = 24, private readonly maxBytes = 2 * 1024 * 1024, private readonly ttlMs = 1500) {}

  invalidate(): void {
    this.generation += 1;
    this.values.clear();
    this.pending.clear();
    this.size = 0;
  }

  async read(key: string, load: () => Promise<Value>): Promise<Value> {
    const cached = this.values.get(key);
    if (cached) {
      if (cached.expires > performance.now()) {
        this.values.delete(key);
        this.values.set(key, cached);
        return structuredClone(cached.value);
      }
      this.values.delete(key);
      this.size -= cached.size;
    }
    const existing = this.pending.get(key);
    if (existing) return structuredClone(await existing);
    const generation = this.generation;
    const promise = load().then((value) => {
      const size = new TextEncoder().encode(JSON.stringify(value)).byteLength;
      if (generation === this.generation && size <= this.maxBytes) {
        while (this.values.size >= this.maxEntries || this.size + size > this.maxBytes) {
          const first = this.values.entries().next().value as [string, Cached<Value>] | undefined;
          if (!first) break;
          this.values.delete(first[0]);
          this.size -= first[1].size;
        }
        this.values.set(key, { value: structuredClone(value), expires: performance.now() + this.ttlMs, size });
        this.size += size;
      }
      return value;
    }).finally(() => { if (this.pending.get(key) === promise) this.pending.delete(key); });
    if (this.pending.size < this.maxEntries) this.pending.set(key, promise);
    return structuredClone(await promise);
  }

  stats(): { entries: number; bytes: number; pending: number } {
    return { entries: this.values.size, bytes: this.size, pending: this.pending.size };
  }
}