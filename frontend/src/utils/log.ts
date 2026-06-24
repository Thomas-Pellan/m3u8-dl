const LOG_RULES: [RegExp, string][] = [
  [/error|failed/i, '#ff5555'],
  [/rate.limited|warning|retry/i, '#ffaa00'],
  [/downloading\.\.\.|segment.*\(\d+%\)/i, '#7ab8ff'],
  [/captured\.|segments captured|complete/i, '#00d7af'],
  [/playlist|intercepted|variant|ready/i, '#00cc66'],
  [/waiting|auto mode|direct mode|intercept mode/i, '#666'],
];

export function logColor(line: string): string {
  return LOG_RULES.find(([re]) => re.test(line))?.[1] ?? '#484848';
}
