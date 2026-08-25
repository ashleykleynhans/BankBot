<script>
  import { onMount } from 'svelte';
  import {
    getBalanceForecast,
    getRecurringPayments,
    checkAffordability,
  } from '../lib/api.js';
  import { formatCurrency, formatDate } from '../lib/stores.js';

  let forecast = null;
  let recurring = null;
  let loading = true;
  let error = null;

  // Affordability simulator state
  let affordAmount = '';
  let affordTiming = '0';
  let affordResult = null;
  let affordChecking = false;
  let affordError = null;

  const TIMING_OPTIONS = [
    { value: '0', label: 'Today' },
    { value: '1', label: 'Tomorrow' },
    { value: '7', label: 'Next week' },
    { value: '30', label: 'Next month' },
  ];

  onMount(async () => {
    try {
      [forecast, recurring] = await Promise.all([
        getBalanceForecast(31, true),
        getRecurringPayments(),
      ]);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
    }
  });

  async function runAffordCheck() {
    const amount = parseFloat(affordAmount);
    if (!amount || amount <= 0) {
      affordError = 'Enter an amount greater than zero.';
      return;
    }
    affordError = null;
    affordChecking = true;
    affordResult = null;
    try {
      affordResult = await checkAffordability(amount, parseInt(affordTiming, 10));
    } catch (err) {
      affordError = err.message;
    } finally {
      affordChecking = false;
    }
  }

  // Chart geometry: map forecast points onto an SVG viewBox.
  const CHART_W = 860;
  const CHART_H = 260;
  const PAD_X = 48;
  const PAD_Y = 20;

  $: points = forecast?.points ?? [];
  $: balances = points.map((p) => p.balance);
  $: minBalance = Math.min(0, ...balances);
  $: maxBalance = Math.max(1, ...balances);
  $: yFor = (value) =>
    PAD_Y +
    ((maxBalance - value) / (maxBalance - minBalance)) * (CHART_H - 2 * PAD_Y);
  $: xFor = (index) =>
    points.length > 1
      ? PAD_X + (index / (points.length - 1)) * (CHART_W - 2 * PAD_X)
      : CHART_W / 2;
  $: chartLine = points.map((p, i) => `${xFor(i)},${yFor(p.balance)}`).join(' ');
  $: chartArea =
    `${PAD_X},${yFor(minBalance)} ` +
    points.map((p, i) => `${xFor(i)},${yFor(p.balance)}`).join(' ') +
    ` ${xFor(points.length - 1)},${yFor(minBalance)}`;
  $: zeroY = yFor(0);

  function severityClass(severity) {
    switch (severity) {
      case 'critical':
        return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400';
      case 'warning':
        return 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-700 text-yellow-700 dark:text-yellow-400';
      case 'ok':
        return 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400';
      default:
        return 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400';
    }
  }
</script>

<div class="p-6 h-full overflow-y-auto">
  <h1 class="text-2xl font-bold mb-6 text-gray-800 dark:text-gray-100">Cashflow Forecast</h1>

  {#if loading}
    <div class="flex items-center justify-center h-64">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  {:else if error}
    <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
      {error}
    </div>
  {:else}
    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">
          Current Balance
          {#if forecast.start_balance_date}
            <span class="text-xs">(as at {formatDate(forecast.start_balance_date)})</span>
          {/if}
        </div>
        <div class="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {forecast.start_balance === null ? '-' : formatCurrency(forecast.start_balance)}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Projected in {forecast.days} days</div>
        <div class="text-2xl font-bold {forecast.end_balance < 0 ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'}">
          {forecast.end_balance === null ? '-' : formatCurrency(forecast.end_balance)}
        </div>
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Lowest Projected Point</div>
        <div class="text-2xl font-bold {(forecast.lowest_balance ?? 0) < 0 ? 'text-red-600 dark:text-red-400' : 'text-gray-900 dark:text-gray-100'}">
          {forecast.lowest_balance === null ? '-' : formatCurrency(forecast.lowest_balance)}
        </div>
        {#if forecast.lowest_date}
          <div class="text-xs text-gray-400 mt-1">{formatDate(forecast.lowest_date)}</div>
        {/if}
      </div>

      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-1">Committed Monthly Outflow</div>
        <div class="text-2xl font-bold text-red-600 dark:text-red-400">
          {formatCurrency(forecast.committed_monthly_outflow)}
        </div>
        <div class="text-xs text-green-600 dark:text-green-400 mt-1">
          Inflow: {formatCurrency(forecast.committed_monthly_inflow)}
        </div>
      </div>
    </div>

    <!-- Risk Alerts -->
    <div class="space-y-3 mb-8">
      {#each forecast.risks as risk}
        <div class="border rounded-lg p-4 text-sm font-medium {severityClass(risk.severity)}">
          {risk.message}
        </div>
      {/each}
    </div>

    <!-- Balance Chart -->
    {#if points.length > 1 && forecast.start_balance !== null}
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 mb-8">
        <h2 class="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">
          Projected Daily Balance
        </h2>
        <svg viewBox="0 0 {CHART_W} {CHART_H}" class="w-full">
          <!-- Zero line -->
          <line
            x1={PAD_X} y1={zeroY} x2={CHART_W - PAD_X} y2={zeroY}
            stroke="#ef4444" stroke-width="1" stroke-dasharray="4 4"
          />
          <text x={CHART_W - PAD_X + 4} y={zeroY + 4} font-size="11" fill="#ef4444">R0</text>
          <!-- Area under the curve -->
          <polygon points={chartArea} fill="rgba(59,130,246,0.08)" />
          <!-- Balance line -->
          <polyline points={chartLine} fill="none" stroke="#3b82f6" stroke-width="2.5" />
          <!-- Points -->
          {#each points as point, i}
            <circle cx={xFor(i)} cy={yFor(point.balance)} r="3"
              fill={(point.balance) < 0 ? '#ef4444' : '#3b82f6'}>
              <title>{formatDate(point.date)}: {formatCurrency(point.balance)}</title>
            </circle>
          {/each}
          <!-- First and last labels -->
          <text x={PAD_X} y={yFor(points[0].balance) - 10} font-size="11" fill="#6b7280">
            {formatCurrency(points[0].balance)}
          </text>
        </svg>
        <p class="text-xs text-gray-400 mt-2">
          Average daily non-recurring spend applied: R{Math.abs(forecast.daily_burn).toFixed(2)}
        </p>
      </div>
    {/if}

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Recurring Payments -->
      <div class="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">
          Recurring Payments ({recurring.items.length})
        </h2>
        {#if recurring.items.length === 0}
          <p class="text-gray-500 dark:text-gray-400 text-sm">
            No recurring payments detected yet. They appear automatically once a
            payment repeats at least three times at a regular interval.
          </p>
        {:else}
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th class="pb-2 pr-4">Merchant</th>
                  <th class="pb-2 pr-4">Cadence</th>
                  <th class="pb-2 pr-4 text-right">Typical</th>
                  <th class="pb-2 pr-4">Next Due</th>
                  <th class="pb-2 text-center">Dir</th>
                </tr>
              </thead>
              <tbody>
                {#each recurring.items.slice(0, 12) as item}
                  <tr class="border-b border-gray-100 dark:border-gray-700/50">
                    <td class="py-2 pr-4 text-gray-800 dark:text-gray-200">
                      {item.merchant}
                      {#if !item.active}
                        <span class="ml-1 text-xs px-1.5 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-500">stopped</span>
                      {:else if item.confidence !== 'high'}
                        <span class="ml-1 text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500">{item.confidence}</span>
                      {/if}
                    </td>
                    <td class="py-2 pr-4 text-gray-500 dark:text-gray-400 capitalize">{item.cadence}</td>
                    <td class="py-2 pr-4 text-right font-medium {item.direction === 'in' ? 'text-green-600 dark:text-green-400' : 'text-gray-800 dark:text-gray-200'}">
                      {item.direction === 'in' ? '+' : '-'}{formatCurrency(item.typical_amount)}
                    </td>
                    <td class="py-2 pr-4 text-gray-500 dark:text-gray-400">{formatDate(item.next_date)}</td>
                    <td class="py-2 text-center">
                      {#if item.direction === 'in'}
                        <span class="text-green-600 dark:text-green-400">&#8593;</span>
                      {:else}
                        <span class="text-red-600 dark:text-red-400">&#8595;</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>

      <!-- Can I Afford It Simulator -->
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6 self-start">
        <h2 class="text-lg font-semibold mb-4 text-gray-800 dark:text-gray-100">Can I Afford It?</h2>
        <label class="block text-sm text-gray-500 dark:text-gray-400 mb-1" for="afford-amount">Amount (R)</label>
        <input
          id="afford-amount"
          type="number"
          min="0"
          step="0.01"
          bind:value={affordAmount}
          placeholder="e.g. 1500"
          class="w-full mb-3 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <label class="block text-sm text-gray-500 dark:text-gray-400 mb-1" for="afford-timing">When</label>
        <select
          id="afford-timing"
          bind:value={affordTiming}
          class="w-full mb-4 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {#each TIMING_OPTIONS as option}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
        <button
          on:click={runAffordCheck}
          disabled={affordChecking}
          class="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium transition-colors"
        >
          {affordChecking ? 'Checking...' : 'Check'}
        </button>

        {#if affordError}
          <div class="mt-4 text-sm text-red-600 dark:text-red-400">{affordError}</div>
        {/if}

        {#if affordResult}
          <div class="mt-4 rounded-lg p-4 text-sm {affordResult.affordable ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : affordResult.affordable === false ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400' : 'bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400'}">
            <div class="font-bold text-base mb-1">
              {affordResult.affordable === true ? 'Yes, you can afford it.' : affordResult.affordable === false ? 'No, not safely.' : ''}
            </div>
            <div>{affordResult.reason}</div>
            {#if affordResult.upcoming_debits_before_target.length > 0}
              <div class="mt-2 text-xs opacity-80">
                Before then: {affordResult.upcoming_debits_before_target.map((d) => `${d.merchant} (${formatCurrency(d.amount)})`).join(', ')}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
