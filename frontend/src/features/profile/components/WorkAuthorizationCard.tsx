import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const WorkAuthorizationCard = () => {
  const { register } = useFormContext<ProfileFormValues>();

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">Work Authorization</h3>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Current Country of Residence</label>
          <input
            {...register('workAuthorization.currentCountry')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Work Authorization Status</label>
          <select
            {...register('workAuthorization.workAuthorization')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select Status</option>
            <option value="Citizen">Citizen</option>
            <option value="Permanent Resident">Permanent Resident</option>
            <option value="GC">GC (Green Card)</option>
            <option value="GC EAD">GC EAD</option>
            <option value="H1B">H1B</option>
            <option value="Work Visa">Work Visa</option>
            <option value="F1 OPT">F1 OPT</option>
            <option value="STEM OPT">STEM OPT</option>
            <option value="Student Visa">Student Visa</option>
            <option value="Asylum Visa">Asylum Visa</option>
            <option value="No Authorization">No Authorization</option>
          </select>
        </div>

        <div className="sm:col-span-2 space-y-3 mt-2">
          <div className="flex items-center">
            <input
              type="checkbox"
              id="sponsorshipRequired"
              {...register('workAuthorization.sponsorshipRequired')}
              className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
            />
            <label htmlFor="sponsorshipRequired" className="ml-2 text-sm text-gray-700 dark:text-gray-300">
              I require sponsorship to work in my target locations now or in the future
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="willingToRelocate"
              {...register('workAuthorization.willingToRelocate')}
              className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
            />
            <label htmlFor="willingToRelocate" className="ml-2 text-sm text-gray-700 dark:text-gray-300">
              I am willing to relocate for the right opportunity
            </label>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="remoteOnly"
              {...register('workAuthorization.remoteOnly')}
              className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
            />
            <label htmlFor="remoteOnly" className="ml-2 text-sm text-gray-700 dark:text-gray-300">
              I am only looking for 100% remote positions
            </label>
          </div>
        </div>
      </div>
    </div>
  );
};
