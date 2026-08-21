import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const JobPreferenceCard = () => {
  const { register } = useFormContext<ProfileFormValues>();

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">Job Preferences</h3>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Work Setup Preferences</label>
          <div className="flex flex-wrap gap-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="pref_remote"
                {...register('preferences.remote')}
                className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
              />
              <label htmlFor="pref_remote" className="ml-2 text-sm text-gray-700 dark:text-gray-300">Remote</label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="pref_hybrid"
                {...register('preferences.hybrid')}
                className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
              />
              <label htmlFor="pref_hybrid" className="ml-2 text-sm text-gray-700 dark:text-gray-300">Hybrid</label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="pref_onsite"
                {...register('preferences.onsite')}
                className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
              />
              <label htmlFor="pref_onsite" className="ml-2 text-sm text-gray-700 dark:text-gray-300">On-site</label>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Travel Percentage</label>
          <select
            {...register('preferences.travelPercentage')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Any</option>
            <option value="0%">0% (No travel)</option>
            <option value="Up to 25%">Up to 25%</option>
            <option value="Up to 50%">Up to 50%</option>
            <option value="Up to 100%">Up to 100%</option>
          </select>
        </div>
      </div>
    </div>
  );
};
