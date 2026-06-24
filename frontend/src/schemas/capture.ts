import { z } from 'zod';

export const urlSchema = z.object({
  url: z.string().min(1, 'URL is required').url('Must be a valid URL'),
});

export const configSchema = z.object({
  output_name: z
    .string()
    .min(1, 'Output name is required')
    .max(200, 'Output name must be under 200 characters')
    .regex(/^[^/\\:*?"<>|]+$/, 'Output name contains invalid filename characters')
    .refine((v) => !v.endsWith('.mp4'), 'Omit the .mp4 extension — it is added automatically'),
  mode: z.enum(['auto', 'direct']),
  quality: z.enum(['best', 'worst']),
  parallel: z.number().int().min(1, 'Min 1 parallel download').max(16, 'Max 16 parallel downloads'),
  scheduled_at: z
    .string()
    .optional()
    .refine((v) => !v || new Date(v) > new Date(), 'Scheduled time must be in the future'),
});

export type UrlFields = z.infer<typeof urlSchema>;
export type ConfigFields = z.infer<typeof configSchema>;
export type FieldErrors = Partial<Record<string, string>>;
