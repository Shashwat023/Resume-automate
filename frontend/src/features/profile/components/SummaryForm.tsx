import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const SummaryForm = () => {
  const { register, watch, formState: { errors } } = useFormContext<ProfileFormValues>();
  
  const summary = watch('summary') || '';

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Professional Summary</h3>
        <span className={`text-xs ${summary.length > 2000 ? 'text-red-500' : 'text-gray-500 dark:text-gray-400'}`}>
          {summary.length} / 2000
        </span>
      </div>
      
      <div>
        <textarea
          {...register('summary')}
          rows={6}
          placeholder="Write a brief professional summary highlighting your key achievements and skills..."
          className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-3 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y"
        />
        {errors.summary && <p className="text-red-500 text-xs mt-1">{errors.summary.message}</p>}
      </div>
    </div>
  );
};
