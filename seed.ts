export function generateSeed(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return Math.abs(hash);
}

export function createDeterministicData<T>(seedInput: string, generator: (index: number) => T, count: number): T[] {
  const baseSeed = generateSeed(seedInput);
  const results: T[] = [];
  for (let i = 0; i < count; i++) {
    results.push(generator(baseSeed + i));
  }
  return results;
}