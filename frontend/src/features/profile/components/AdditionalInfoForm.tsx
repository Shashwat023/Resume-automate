import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const AdditionalInfoForm = () => {
  const { register } = useFormContext<ProfileFormValues>();

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Diversity & Additional Info</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          These fields are optional but frequently requested by ATS systems. We use them strictly for auto-filling application forms when required.
        </p>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Veteran Status</label>
          <select
            {...register('additional.veteranStatus')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select Status</option>
            <option value="I am not a protected veteran">I am not a protected veteran</option>
            <option value="I identify as one or more of the classifications of a protected veteran">I am a protected veteran</option>
            <option value="I don't wish to answer">I don't wish to answer</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Disability Status</label>
          <select
            {...register('additional.disabilityStatus')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select Status</option>
            <option value="Yes, I have a disability">Yes, I have a disability</option>
            <option value="No, I don't have a disability">No, I don't have a disability</option>
            <option value="I don't wish to answer">I don't wish to answer</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Gender Identity</label>
          <select
            {...register('additional.genderIdentity')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select Identity</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
            <option value="Non-binary">Non-binary</option>
            <option value="I don't wish to answer">I don't wish to answer</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Race / Ethnicity</label>
          <select
            {...register('additional.raceEthnicity')}
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Select Ethnicity</option>
            <option value="Hispanic or Latino">Hispanic or Latino</option>
            <option value="White (Not Hispanic or Latino)">White</option>
            <option value="Black or African American">Black or African American</option>
            <option value="Asian">Asian</option>
            <option value="Two or More Races">Two or More Races</option>
            <option value="I don't wish to answer">I don't wish to answer</option>
          </select>
        </div>
      </div>
    </div>
  );
};
