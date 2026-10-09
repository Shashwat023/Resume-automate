import { useThemeStore } from '../store/themeStore';
import {
  useSettingsStore,
  QUEUE_POLLING_OPTIONS,
} from '../store/settingsStore';
import { useProfileStore } from '../store/profileStore';
import { downloadJson } from '@/lib/exportJson';
import { Settings, Moon, Sun, Monitor, PlayCircle, ShieldAlert, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { clsx } from 'clsx';
import { motion } from 'framer-motion';

export const SettingsPage = () => {
  const { theme, setTheme } = useThemeStore();
  const exportProfile = useProfileStore((state) => state.exportProfile);
  const pollingIntervalMs = useSettingsStore((s) => s.queuePollingIntervalMs);
  const setPollingIntervalMs = useSettingsStore((s) => s.setQueuePollingIntervalMs);

  const handleClearCache = () => {
    localStorage.clear();
    toast.success('Local cache cleared. Reloading application...');
    setTimeout(() => {
      window.location.reload();
    }, 1500);
  };

  const handleExportData = () => {
    downloadJson(exportProfile(), 'auto-apply-data-backup.json');
    toast.success('Application data exported');
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl mx-auto h-full flex flex-col space-y-8 pb-12"
    >
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <Settings className="w-6 h-6" /> Application Settings
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Manage your platform preferences and automation configuration.
        </p>
      </div>

      <div className="space-y-6">
        
        {/* Appearance Section */}
        <section className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Appearance</h2>
          
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <button
              onClick={() => setTheme('light')}
              className={clsx(
                "flex flex-col items-center gap-3 p-4 rounded-xl border-2 transition-all",
                theme === 'light' ? "border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20" : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
              )}
            >
              <Sun className="w-6 h-6 text-gray-700 dark:text-gray-300" />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Light</span>
            </button>
            <button
              onClick={() => setTheme('dark')}
              className={clsx(
                "flex flex-col items-center gap-3 p-4 rounded-xl border-2 transition-all",
                theme === 'dark' ? "border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20" : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
              )}
            >
              <Moon className="w-6 h-6 text-gray-700 dark:text-gray-300" />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Dark</span>
            </button>
            <button
              onClick={() => setTheme('system')}
              className={clsx(
                "flex flex-col items-center gap-3 p-4 rounded-xl border-2 transition-all",
                theme === 'system' ? "border-indigo-600 bg-indigo-50 dark:bg-indigo-900/20" : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
              )}
            >
              <Monitor className="w-6 h-6 text-gray-700 dark:text-gray-300" />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">System</span>
            </button>
          </div>
        </section>

        {/* Automation Preferences */}
        <section className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4 flex items-center gap-2">
            <PlayCircle className="w-5 h-5 text-indigo-500" /> Auto Apply Configuration
          </h2>
          
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">Queue Polling Interval</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">How often the frontend checks backend status.</p>
              </div>
              <select
                value={pollingIntervalMs}
                onChange={(e) => setPollingIntervalMs(Number(e.target.value))}
                className="rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {QUEUE_POLLING_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Danger Zone */}
        <section className="bg-red-50 dark:bg-red-900/10 rounded-xl p-6 border border-red-200 dark:border-red-900/30">
          <h2 className="text-lg font-semibold text-red-700 dark:text-red-400 mb-4 flex items-center gap-2">
            <ShieldAlert className="w-5 h-5" /> Danger Zone
          </h2>
          
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">Export Application Data</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Download a JSON backup of your profile and settings.</p>
              </div>
              <button 
                onClick={handleExportData}
                className="px-4 py-2 border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Export Data
              </button>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-red-200 dark:border-red-900/30">
              <div>
                <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">Clear Local Cache</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Reset all local preferences and UI states. (Does not delete backend data).</p>
              </div>
              <button 
                onClick={handleClearCache}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
              >
                <Trash2 className="w-4 h-4" /> Clear Cache
              </button>
            </div>
          </div>
        </section>

      </div>
    </motion.div>
  );
};
