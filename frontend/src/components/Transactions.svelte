<script>
  import { onMount } from 'svelte';
  import {
    getTransactions,
    searchTransactions,
    getCategories,
    getTransactionsByCategory,
  } from '../lib/api.js';
  import { formatCurrency, formatDate, filterCategory, filterSource, currentPage } from '../lib/stores.js';

  // Generate unique color for each category using HSL
  // Uses golden angle to distribute hues evenly for any number of categories
  let categoryColorMap = new Map();

  function hslToRgb(h, s, l) {
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs((h / 60) % 2 - 1));
    const m = l - c / 2;
    let r, g, b;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
  }

  function generateCategoryColor(index, total) {
    // Use golden angle (137.5°) for optimal color distribution
    const goldenAngle = 137.508;
    const hue = (index * goldenAngle) % 360;
    const saturation = 0.7;
    const lightness = 0.5;

    const [r1, g1, b1] = hslToRgb(hue, saturation, lightness);
    const [r2, g2, b2] = hslToRgb(hue, saturation, lightness - 0.15);

    return {
      gradient: `linear-gradient(135deg, rgb(${r1},${g1},${b1}), rgb(${r2},${g2},${b2}))`,
      shadow: `0 4px 14px rgba(${r1},${g1},${b1}, 0.4)`
    };
  }

  function buildColorMap(categoryList) {
    categoryColorMap = new Map();
    const sorted = [...categoryList].sort();
    sorted.forEach((cat, index) => {
      categoryColorMap.set(cat, generateCategoryColor(index, sorted.length));
    });
  }

  function getCategoryStyle(category) {
    if (!category) {
      return { background: '#4b5563', boxShadow: 'none' };
    }

    // Fallback if category not in map yet
    if (!categoryColorMap.has(category)) {
      categoryColorMap.set(category, generateCategoryColor(categoryColorMap.size, categoryColorMap.size + 1));
    }

    const color = categoryColorMap.get(category);
    return { background: color.gradient, boxShadow: color.shadow };
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  let transactions = [];
  let total = 0;
  let loading = true;
  let error = null;

  let searchQuery = '';
  let searchTimeout;

  let categories = [];
  let selectedCategory = '';

  const PAGE_SIZE = 20;
  let pageNum = 0;

  $: totalPages = Math.ceil(total / PAGE_SIZE);
  $: canGoBack = pageNum > 0;
  $: canGoForward = pageNum < totalPages - 1;

  onMount(async () => {
    await loadCategories();

    // Check if there's a filter from Dashboard navigation
    const initialFilter = $filterCategory;
    if (initialFilter) {
      selectedCategory = initialFilter;
      filterCategory.set(''); // Clear the store
      await handleCategoryChange();
    } else {
      await loadTransactions();
    }
  });

  async function loadTransactions() {
    loading = true;
    error = null;
    try {
      const result = await getTransactions(PAGE_SIZE, pageNum * PAGE_SIZE);
      transactions = result.transactions;
      total = result.total;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  async function loadCategories() {
    try {
      const result = await getCategories();
      categories = result.categories;
      buildColorMap(categories);
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      selectedCategory = '';
      pageNum = 0;
      await loadTransactions();
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await searchTransactions(searchQuery);
      transactions = result.transactions;
      total = result.count;
      pageNum = 0;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function handleSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(handleSearch, 300);
  }

  async function handleCategoryChange() {
    searchQuery = '';
    pageNum = 0;

    if (!selectedCategory) {
      await loadTransactions();
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await getTransactionsByCategory(selectedCategory);
      transactions = result.transactions;
      total = result.count;
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function filterByCategory(category) {
    if (category) {
      selectedCategory = category;
      filterSource.set('transactions');
      handleCategoryChange();
    }
  }

  function clearFilter() {
    const source = $filterSource;
    selectedCategory = '';
    filterSource.set('');

    if (source && source !== 'transactions') {
      currentPage.set(source);
    } else {
      handleCategoryChange();
    }
  }

  async function goToPage(page) {
    if (page < 0 || page >= totalPages) return;
    pageNum = page;
    if (!searchQuery && !selectedCategory) {
      await loadTransactions();
    }
  }
</script>

<div class="p-6 h-full overflow-y-auto">
  <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-gray-100">Transactions</h1>

  <!-- Filters -->
  <div class="flex flex-col sm:flex-row gap-4 mb-6">
    <!-- Search -->
    <div class="flex-1">
      <input
        type="text"
        bind:value={searchQuery}
        on:input={handleSearchInput}
        placeholder="Search transactions..."
        class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    </div>

    <!-- Category filter -->
    <select
      bind:value={selectedCategory}
      on:change={handleCategoryChange}
      class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <option value="">All Categories</option>
      {#each categories as category}
        <option value={category}>{category}</option>
      {/each}
    </select>
  </div>

  <!-- Active filter indicator -->
  {#if selectedCategory}
    <div class="flex items-center gap-2 mb-4">
      <span class="text-sm text-gray-500 dark:text-gray-400">Filtered by:</span>
      <button
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-white cursor-pointer transition-all hover:scale-105"
        style="background: {getCategoryStyle(selectedCategory).background}; box-shadow: {getCategoryStyle(selectedCategory).boxShadow};"
        on:click={clearFilter}
      >
        {formatCategoryName(selectedCategory)}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  {/if}

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if error}
    <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
      {error}
    </div>
  {:else}
    <!-- Results count -->
    <div class="text-sm text-gray-500 dark:text-gray-400 mb-4">
      Showing {transactions.length} of {total} transactions
    </div>

    <!-- Table -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50 dark:bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Date
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Stmt
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Description
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Amount
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                Category
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            {#each transactions as tx}
              <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  {formatDate(tx.date)}
                </td>
                <td class="px-4 py-3 text-sm text-center text-gray-500 dark:text-gray-500 whitespace-nowrap">
                  {tx.statement_number || '-'}
                </td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                  {tx.description}
                </td>
                <td class="px-4 py-3 text-sm text-right whitespace-nowrap font-medium {tx.transaction_type === 'debit' ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}">
                  {tx.transaction_type === 'debit' ? '-' : '+'}{formatCurrency(tx.amount)}
                </td>
                <td class="px-4 py-3 text-sm">
                  <button
                    class="category-badge"
                    style="background: {getCategoryStyle(tx.category).background}; box-shadow: {getCategoryStyle(tx.category).boxShadow};"
                    on:click={() => filterByCategory(tx.category)}
                    title="View all {formatCategoryName(tx.category)} transactions"
                  >
                    {formatCategoryName(tx.category)}
                  </button>
                </td>
              </tr>
            {:else}
              <tr>
                <td colspan="5" class="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No transactions found
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagination -->
    {#if totalPages > 1 && !searchQuery && !selectedCategory}
      <div class="flex items-center justify-between mt-4">
        <button
          on:click={() => goToPage(pageNum - 1)}
          disabled={!canGoBack}
          class="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Previous
        </button>
        <span class="text-sm text-gray-600 dark:text-gray-400">
          Page {pageNum + 1} of {totalPages}
        </span>
        <button
          on:click={() => goToPage(pageNum + 1)}
          disabled={!canGoForward}
          class="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .category-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.375rem 0.875rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 700;
    color: white;
    letter-spacing: 0.05em;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.15);
    backdrop-filter: blur(4px);
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    white-space: nowrap;
    cursor: pointer;
  }

  .category-badge:hover {
    transform: translateY(-2px) scale(1.05);
    filter: brightness(1.1);
    border-color: rgba(255, 255, 255, 0.3);
  }

  .category-badge:active {
    transform: translateY(0) scale(0.98);
  }
</style>
