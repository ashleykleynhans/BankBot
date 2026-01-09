/**
 * Shared application stores.
 */
import { writable } from 'svelte/store';

// Current page/view
export const currentPage = writable('chat');

// Category filter (shared between Dashboard and Transactions)
export const filterCategory = writable('');

// Track where filter was applied from (for back navigation)
export const filterSource = writable('');

// Available pages
export const pages = ['chat', 'dashboard', 'transactions'];

// Format currency (South African Rand)
export function formatCurrency(amount) {
  return new Intl.NumberFormat('en-ZA', {
    style: 'currency',
    currency: 'ZAR',
  }).format(amount);
}

// Format date
export function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-ZA', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}
