<script>
  import { onMount } from 'svelte';
  import { getStatements, getLatestAnalytics, getAnalyticsByStatement } from '../lib/api.js';
  import { formatCurrency, currentPage, filterCategory, filterSource } from '../lib/stores.js';
  import PieChart from './PieChart.svelte';

  let statements = [];
  let selectedStatementNumber = null;
  let analytics = null;
  let loading = true;
  let error = null;

  onMount(async () => {
    try {
      // Load statements for dropdown
      const statementsData = await getStatements();
      statements = statementsData.statements || [];

      // Load analytics for latest statement
      analytics = await getLatestAnalytics();
      if (analytics?.statement_number) {
        selectedStatementNumber = analytics.statement_number;
      }
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  });

  async function handleStatementChange(event) {
    const statementNumber = event.target.value;
    if (!statementNumber) return;

    selectedStatementNumber = statementNumber;
    loading = true;
    error = null;

    try {
      analytics = await getAnalyticsByStatement(statementNumber);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  }

  function handleCategorySelect(event) {
    const { category } = event.detail;
    filterCategory.set(category);
    filterSource.set('analytics');
    currentPage.set('transactions');
  }

  function formatStatementLabel(stmt) {
    const num = stmt.statement_number || 'N/A';
    const date = stmt.statement_date
      ? new Date(stmt.statement_date).toLocaleDateString('en-ZA', { month: 'short', year: 'numeric' })
      : '';
    return `#${num}${date ? ` - ${date}` : ''}`;
  }

  // Prepare data for pie chart
  $: pieData = (analytics?.categories || [])
    .filter(c => c.total_debits > 0)
    .map(c => ({
      category: c.category,
      value: c.total_debits,
      count: c.count
    }));

  // Find top category
  $: topCategory = pieData.length > 0
    ? pieData.reduce((a, b) => a.value > b.value ? a : b)
    : null;

  // Format header with month and statement number
  $: headerSubtitle = (() => {
    if (!analytics) return '';
    const num = analytics.statement_number || '';
    const date = analytics.statement_date
      ? new Date(analytics.statement_date).toLocaleDateString('en-ZA', { month: 'long', year: 'numeric' })
      : '';
    if (num && date) return `Statement #${num} - ${date}`;
    if (num) return `Statement #${num}`;
    if (date) return date;
    return '';
  })();
</script>

<div class="p-6 h-full overflow-y-auto">
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">Analytics</h1>
      {#if headerSubtitle && !loading}
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{headerSubtitle}</p>
      {/if}
    </div>

    <!-- Statement Selector -->
    {#if statements.length > 0}
      <select
        class="px-4 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        value={selectedStatementNumber}
        on:change={handleStatementChange}
      >
        {#each statements as stmt}
          <option value={stmt.statement_number}>
            {formatStatementLabel(stmt)}
          </option>
        {/each}
      </select>
    {/if}
  </div>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if error}
    {#if error.includes('No bank statements imported')}
      <div class="flex flex-col items-center justify-center h-64 text-gray-500 dark:text-gray-400">
        <svg class="w-16 h-16 mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <p class="text-lg font-medium">No bank statements imported</p>
        <div class="mt-3 text-sm text-left bg-gray-100 dark:bg-gray-800 rounded-lg p-4 max-w-md">
          <p class="mb-2">To get started:</p>
          <ol class="list-decimal list-inside space-y-1">
            <li>Place your bank statement PDFs in the <code class="bg-gray-200 dark:bg-gray-700 px-1 rounded">statements/</code> directory</li>
            <li>Run <code class="bg-gray-200 dark:bg-gray-700 px-1 rounded">bankbot import</code></li>
          </ol>
        </div>
      </div>
    {:else}
      <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
        {error}
      </div>
    {/if}
  {:else if analytics}
    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Total Spent</div>
        <div class="text-2xl font-bold text-red-600 dark:text-red-400">
          {formatCurrency(analytics.total_debits || 0)}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Transactions</div>
        <div class="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {analytics.transaction_count?.toLocaleString() || 0}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Top Category</div>
        <div class="text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
          {topCategory ? topCategory.category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : '-'}
        </div>
        {#if topCategory}
          <div class="text-sm text-gray-500 dark:text-gray-400">
            {formatCurrency(topCategory.value)}
          </div>
        {/if}
      </div>
    </div>

    <!-- Pie Chart Section -->
    {#if pieData.length > 0}
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold mb-6 text-gray-800 dark:text-gray-100">Spending Breakdown</h2>
        <PieChart data={pieData} on:select={handleCategorySelect} />
      </div>
    {:else}
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 text-center text-gray-500 dark:text-gray-400">
        No spending data available for this statement.
      </div>
    {/if}

    <!-- Income Section -->
    {#if analytics.total_credits > 0}
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mt-6">
        <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-gray-100">Income</h2>
        <div class="text-2xl font-bold text-green-600 dark:text-green-400">
          {formatCurrency(analytics.total_credits)}
        </div>
      </div>
    {/if}
  {:else}
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 text-center text-gray-500 dark:text-gray-400">
      No analytics data available. Import some statements first.
    </div>
  {/if}
</div>
