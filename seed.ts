export function generateSeedData(seed: number, count: number): number[] {
  const result: number[] = [];
  let current = seed;
  const a = 1664525;
  const c = 1013904223;
  const m = 4294967296;

  for (let i = 0; i < count; i++) {
    current = (a * current + c) % m;
    result.push(current);
  }
  return result;
}