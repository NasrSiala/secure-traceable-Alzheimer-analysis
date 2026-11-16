/**
 * A variable that is set but empty counts as unset, and a value is trimmed (a CRLF `.env` leaves a
 * carriage return at the end of every line). An `env_file:` or `--env-file` copy of
 * `.env.example` sets every listed key, and `??` would keep the empty string over the default.
 */
export function envSetting(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  if (value === undefined || value === "") {
    return fallback;
  }
  return value;
}
