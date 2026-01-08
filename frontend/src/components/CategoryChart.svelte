<script>
  import { createEventDispatcher } from 'svelte';
  import { formatCurrency } from '../lib/stores.js';

  export let categories = [];

  const dispatch = createEventDispatcher();

  // Calculate max value for scaling
  $: maxDebit = Math.max(...categories.map((c) => c.total_debits || 0), 1);

  // Sort by total debits descending
  $: sortedCategories = [...categories]
    .filter((c) => c.total_debits > 0)
    .sort((a, b) => b.total_debits - a.total_debits);

  // Generate unique colors using HSL with golden angle distribution
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

  function generateCategoryColor(index) {
    const goldenAngle = 137.508;
    const hue = (index * goldenAngle) % 360;
    const [r1, g1, b1] = hslToRgb(hue, 0.7, 0.5);
    const [r2, g2, b2] = hslToRgb(hue, 0.7, 0.35);
    return {
      gradient: `linear-gradient(135deg, rgb(${r1},${g1},${b1}), rgb(${r2},${g2},${b2}))`
    };
  }

  let categoryColorMap = new Map();

  $: {
    categoryColorMap = new Map();
    const allCats = categories.map(c => c.category).filter(Boolean).sort();
    allCats.forEach((cat, index) => {
      categoryColorMap.set(cat, generateCategoryColor(index));
    });
  }

  function getBarStyle(category) {
    if (!category) return { background: '#4b5563' };
    const color = categoryColorMap.get(category);
    return { background: color?.gradient || '#4b5563' };
  }

  function formatCategoryName(category) {
    if (!category) return 'Uncategorized';
    return category
      .replace(/_/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  function handleClick(category) {
    dispatch('select', { category });
  }
</script>

<div class="space-y-2">
  {#each sortedCategories as category}
    {@const percentage = ((category.total_debits / maxDebit) * 100).toFixed(0)}
    <button
      class="w-full flex items-center gap-4 p-2 -mx-2 rounded-lg transition-all hover:bg-gray-100 dark:hover:bg-gray-700/50 cursor-pointer group"
      on:click={() => handleClick(category.category)}
      title="View {formatCategoryName(category.category)} transactions"
    >
      <div class="w-32 text-sm text-gray-600 dark:text-gray-400 truncate text-left group-hover:text-gray-900 dark:group-hover:text-gray-200 transition-colors">
        {formatCategoryName(category.category)}
      </div>
      <div class="flex-1 h-7 bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden shadow-inner">
        <div
          class="h-full rounded-lg transition-all duration-300 group-hover:opacity-90"
          style="width: {percentage}%; background: {getBarStyle(category.category).background};"
        ></div>
      </div>
      <div class="w-28 text-sm text-right text-gray-700 dark:text-gray-300 font-medium">
        {formatCurrency(category.total_debits)}
      </div>
      <div class="w-16 text-xs text-right text-gray-500 dark:text-gray-400">
        ({category.count})
      </div>
      <svg class="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
    </button>
  {/each}

  {#if sortedCategories.length === 0}
    <p class="text-gray-500 dark:text-gray-400 text-center py-4">No spending data available</p>
  {/if}
</div>
