import { useState } from 'react';
import { adminApi, type SyncResult } from '@/api/admin';
import {
  useAdminStatsQuery,
  useTrackedSyncStatusQuery,
  useStartTrackedSyncMutation,
  usePauseTrackedSyncMutation,
} from '@/features/admin/services/admin.queries';
import {
  Globe, Play, CheckCircle, XCircle, RefreshCw, Pause,
  Database, TrendingUp, Clock, AlertTriangle, Plus, Trash2, ListChecks
} from 'lucide-react';
import { toast } from 'sonner';

export const AdminPage = () => {
  const [urls, setUrls] = useState<string[]>(['']);
  const [results, setResults] = useState<SyncResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const { data: stats, refetch: refetchStats } = useAdminStatsQuery();
  const { data: trackedSync } = useTrackedSyncStatusQuery();
  const startTrackedSync = useStartTrackedSyncMutation();
  const pauseTrackedSync = usePauseTrackedSyncMutation();

  const trackedSyncStatus = trackedSync?.status ?? 'idle';
  const trackedSyncIsRunning = trackedSyncStatus === 'running';
  const trackedSyncStartLabel =
    trackedSyncStatus === 'paused' ? 'Resume Syncing' : 'Start Syncing Tracked Companies';

  const addUrl = () => setUrls(prev => [...prev, '']);
  const removeUrl = (i: number) => setUrls(prev => prev.filter((_, idx) => idx !== i));
  const updateUrl = (i: number, val: string) =>
    setUrls(prev => prev.map((u, idx) => (idx === i ? val : u)));

  const handleSync = async () => {
    const validUrls = urls.map(u => u.trim()).filter(Boolean);
    if (!validUrls.length) {
      toast.error('Please enter at least one company URL');
      return;
    }

    setIsRunning(true);
    setResults([]);

    for (const url of validUrls) {
      try {
        const result = await adminApi.syncCompany(url);
        setResults(prev => [...prev, result]);
        if (result.success) {
          toast.success(`✓ ${url} — ${result.jobs_inserted} inserted, ${result.jobs_updated} updated`);
        } else {
          toast.error(`✗ Failed to scrape ${url}`);
        }
      } catch (err: any) {
        setResults(prev => [
          ...prev,
          {
            company_url: url,
            success: false,
            jobs_inserted: 0,
            jobs_updated: 0,
            failed: 1,
            timestamp: new Date().toISOString(),
          },
        ]);
        toast.error(`Error scraping ${url}: ${err.message}`);
      }
    }

    setIsRunning(false);
    refetchStats();
  };

  const totalInserted = results.reduce((a, r) => a + r.jobs_inserted, 0);
  const totalUpdated = results.reduce((a, r) => a + r.jobs_updated, 0);
  const totalFailed = results.filter(r => !r.success).length;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">

      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin Panel</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Scrape company job portals and sync them into the database.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] p-5 flex items-center gap-4">
          <div className="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-900/20">
            <Database className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Total Jobs in DB</p>
            <p className="text-2xl font-bold">{stats?.total_jobs?.toLocaleString() ?? '—'}</p>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] p-5 flex items-center gap-4">
          <div className="p-2 rounded-lg bg-green-50 dark:bg-green-900/20">
            <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Inserted This Session</p>
            <p className="text-2xl font-bold text-green-600 dark:text-green-400">{totalInserted}</p>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] p-5 flex items-center gap-4">
          <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-900/20">
            <RefreshCw className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Updated This Session</p>
            <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">{totalUpdated}</p>
          </div>
        </div>
      </div>

      {/* Tracked Companies Bulk Sync */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-indigo-500" />
            Sync All Tracked Companies
          </h2>
          {trackedSync && trackedSync.total_eligible > 0 && (
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              {trackedSync.processed} / {trackedSync.total_eligible} companies
            </span>
          )}
        </div>

        <p className="text-sm text-gray-500 dark:text-gray-400">
          Scrapes every company listed in <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded">config/portals.yml</code>,
          not just a URL you paste below. A company already synced recently is skipped automatically, so
          re-running this only picks up newly-posted jobs. This can take hours across hundreds of companies —
          pause any time and resume later from exactly where it left off, even after restarting the server.
        </p>

        {trackedSync && trackedSync.total_eligible > 0 && (
          <div className="space-y-2">
            <div className="w-full h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all duration-500"
                style={{
                  width: `${Math.round((trackedSync.processed / trackedSync.total_eligible) * 100)}%`,
                }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
              <span className="text-green-600 dark:text-green-400 font-medium">+{trackedSync.jobs_inserted} inserted</span>
              <span className="text-amber-600 dark:text-amber-400 font-medium">~{trackedSync.jobs_updated} updated</span>
              {trackedSync.companies_failed > 0 && (
                <span className="text-red-500 font-medium">{trackedSync.companies_failed} companies failed</span>
              )}
              {trackedSyncIsRunning && trackedSync.current_company_name && (
                <span className="flex items-center gap-1">
                  <RefreshCw className="w-3 h-3 animate-spin" />
                  Currently syncing: <strong className="text-gray-700 dark:text-gray-300">{trackedSync.current_company_name}</strong>
                </span>
              )}
              {trackedSyncStatus === 'paused' && (
                <span className="text-amber-600 dark:text-amber-400 font-medium">Paused</span>
              )}
              {trackedSyncStatus === 'completed' && (
                <span className="text-green-600 dark:text-green-400 font-medium">
                  <CheckCircle className="w-3 h-3 inline mr-1" /> Pass complete
                </span>
              )}
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => startTrackedSync.mutate()}
            disabled={trackedSyncIsRunning || startTrackedSync.isPending}
            className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors text-sm"
          >
            {trackedSyncIsRunning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                {trackedSyncStartLabel}
              </>
            )}
          </button>
          {trackedSyncIsRunning && (
            <button
              onClick={() => pauseTrackedSync.mutate()}
              disabled={pauseTrackedSync.isPending}
              className="flex items-center justify-center gap-2 px-6 py-3 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 text-gray-700 dark:text-gray-300 font-semibold rounded-lg transition-colors text-sm"
            >
              <Pause className="w-4 h-4" />
              Pause
            </button>
          )}
        </div>
      </div>

      {/* URL Input Panel */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold flex items-center gap-2">
              <Globe className="w-4 h-4 text-indigo-500" />
              Company URLs to Scrape
            </h2>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              For a one-off company not in portals.yml, or to re-check it right now.
            </p>
          </div>
          <button
            onClick={addUrl}
            disabled={isRunning}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
          >
            <Plus className="w-3.5 h-3.5" /> Add URL
          </button>
        </div>

        <div className="space-y-2">
          {urls.map((url, i) => (
            <div key={i} className="flex gap-2">
              <div className="flex-1 relative">
                <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="url"
                  value={url}
                  onChange={e => updateUrl(i, e.target.value)}
                  placeholder="https://www.company.com/"
                  disabled={isRunning}
                  className="w-full pl-9 pr-4 py-2.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
                />
              </div>
              {urls.length > 1 && (
                <button
                  onClick={() => removeUrl(i)}
                  disabled={isRunning}
                  className="p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-300 dark:hover:border-red-800 text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>

        <button
          onClick={handleSync}
          disabled={isRunning || urls.every(u => !u.trim())}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors text-sm"
        >
          {isRunning ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Scraping... ({results.length}/{urls.filter(u => u.trim()).length} done) — this may take several minutes
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              Start Scraping
            </>
          )}
        </button>
      </div>

      {/* Results Table */}
      {results.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#18181b] overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
            <h2 className="text-base font-semibold">Scrape Results</h2>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 font-medium">
                <CheckCircle className="w-3.5 h-3.5" />
                {results.filter(r => r.success).length} succeeded
              </span>
              {totalFailed > 0 && (
                <span className="flex items-center gap-1 text-red-500 font-medium">
                  <XCircle className="w-3.5 h-3.5" />
                  {totalFailed} failed
                </span>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50">
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Status</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Company URL</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Inserted</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Updated</th>
                  <th className="text-left px-6 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {results.map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50 dark:hover:bg-gray-900/30 transition-colors">
                    <td className="px-6 py-4">
                      {r.success ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                          <CheckCircle className="w-3 h-3" /> Success
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
                          <XCircle className="w-3 h-3" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <a
                        href={r.company_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 dark:text-indigo-400 hover:underline truncate max-w-xs block"
                      >
                        {r.company_url}
                      </a>
                    </td>
                    <td className="px-4 py-4 text-center">
                      <span className="font-semibold text-green-600 dark:text-green-400">
                        +{r.jobs_inserted}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-center">
                      <span className="font-semibold text-amber-600 dark:text-amber-400">
                        ~{r.jobs_updated}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-400 dark:text-gray-500 text-xs">
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(r.timestamp).toLocaleTimeString()}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
              {results.length > 1 && (
                <tfoot>
                  <tr className="border-t-2 border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 font-semibold">
                    <td className="px-6 py-3 text-xs text-gray-500 uppercase">Total</td>
                    <td className="px-6 py-3"></td>
                    <td className="px-4 py-3 text-center text-green-600 dark:text-green-400">+{totalInserted}</td>
                    <td className="px-4 py-3 text-center text-amber-600 dark:text-amber-400">~{totalUpdated}</td>
                    <td className="px-6 py-3"></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>
      )}

      {/* Warning */}
      <div className="flex items-start gap-3 p-4 rounded-xl border border-amber-200 dark:border-amber-800/50 bg-amber-50 dark:bg-amber-900/10">
        <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
        <p className="text-sm text-amber-800 dark:text-amber-300">
          Scraping uses Browser-Use AI agent and may take <strong>2–10 minutes per company</strong> depending on the size of their job board. The page will update as each company completes.
        </p>
      </div>

    </div>
  );
};