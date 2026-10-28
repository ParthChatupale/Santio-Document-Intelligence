import type { ProviderRetry } from './types';

export function retryMessage(retry: ProviderRetry, now: number): string {
  const seconds = Math.max(0, Math.ceil((Date.parse(retry.retry_at) - now) / 1000));
  const reason = retry.reason === 'rate_limit' ? 'NVIDIA is temporarily rate-limiting requests.' : 'The model service is temporarily unavailable.';
  const delay = Number.isFinite(seconds) && seconds > 0 ? `in ${seconds} seconds` : 'shortly';
  return `${reason} Retrying ${retry.stage} ${delay} · retry ${retry.retry_number} of ${retry.maximum_retries}.`;
}
