import { clsx, type ClassValue } from 'clsx';

/** Merge CSS class names conditionally */
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

/** Format a date string to a locale-friendly format */
export function formatDate(
  date: string | Date,
  locale = 'fr-FR',
  options: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }
): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString(locale, options);
}

/** Format a monetary amount */
export function formatAmount(amount: number, currency = 'EUR', locale = 'fr-FR'): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

/** Format a confidence score as a percentage string */
export function formatScore(score: number): string {
  return `${Math.round(score)}%`;
}

/** Truncate a string to a maximum length */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return `${str.slice(0, maxLength - 3)}...`;
}

/** Debounce a function */
export function debounce<T extends (...args: unknown[]) => void>(fn: T, delay: number): T {
  let timer: ReturnType<typeof setTimeout>;
  return ((...args: Parameters<T>) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  }) as T;
}

/** Get initials from a full name */
export function getInitials(firstName: string, lastName: string): string {
  return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
}
