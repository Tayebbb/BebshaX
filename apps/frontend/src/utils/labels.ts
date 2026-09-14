/** Human labels for machine tokens the persona corpus stores
 * (`postsecondary_teacher`, `bachelors`, `not_in_workforce`). Never invents a
 * value: unknown or empty input comes back unchanged/empty. */
const SPECIAL: Record<string, string> = {
  bachelors: "Bachelor's degree",
  masters: "Master's degree",
  doctorate: 'Doctorate',
  associates: "Associate's degree",
  high_school: 'High school',
  some_college: 'Some college',
  not_in_workforce: 'Not in the workforce',
  unemployed: 'Unemployed',
  retired: 'Retired',
};

export function humanizeToken(value: string | null | undefined): string {
  if (typeof value !== 'string') return '';
  const trimmed = value.trim();
  if (!trimmed) return '';
  const lower = trimmed.toLowerCase();
  if (SPECIAL[lower]) return SPECIAL[lower];
  if (!/[_]/.test(trimmed) && /\s|[A-Z].*[a-z]/.test(trimmed)) return trimmed; // already prose
  const words = trimmed.replace(/_or_/g, ' or ').split(/[_\s]+/).filter(Boolean);
  return words
    .map((word, index) => (index === 0 ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : word.toLowerCase()))
    .join(' ');
}
