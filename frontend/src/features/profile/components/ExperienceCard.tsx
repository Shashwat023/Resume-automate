import { useFormContext, useFieldArray } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';
import { Plus, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export const ExperienceCard = () => {
  const { register, control, watch, formState: { errors } } = useFormContext<ProfileFormValues>();
  
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'employment',
  });

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Employment History</h3>
        <button
          type="button"
          onClick={() => append({ company: '', role: '', location: '', startDate: '', currentlyWorking: false })}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/30 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors"
        >
          <Plus className="w-4 h-4" /> Add Experience
        </button>
      </div>

      <div className="space-y-6">
        <AnimatePresence initial={false}>
          {fields.map((field, index) => {
            const currentlyWorking = watch(`employment.${index}.currentlyWorking`);

            return (
              <motion.div
                key={field.id}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="relative p-5 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => remove(index)}
                  className="absolute top-4 right-4 text-gray-400 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Company *</label>
                    <input
                      {...register(`employment.${index}.company`)}
                      className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    {errors.employment?.[index]?.company && <p className="text-red-500 text-xs mt-1">{errors.employment[index]?.company?.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Role / Job Title *</label>
                    <input
                      {...register(`employment.${index}.role`)}
                      className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    {errors.employment?.[index]?.role && <p className="text-red-500 text-xs mt-1">{errors.employment[index]?.role?.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Location</label>
                    <input
                      {...register(`employment.${index}.location`)}
                      placeholder="e.g. New York, NY (Remote)"
                      className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Start Date *</label>
                    <input
                      type="month"
                      {...register(`employment.${index}.startDate`)}
                      className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    {errors.employment?.[index]?.startDate && <p className="text-red-500 text-xs mt-1">{errors.employment[index]?.startDate?.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">End Date</label>
                    <input
                      type="month"
                      disabled={currentlyWorking}
                      {...register(`employment.${index}.endDate`)}
                      className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                    />
                  </div>

                  <div className="sm:col-span-2 flex items-center">
                    <input
                      type="checkbox"
                      id={`currentWork_${index}`}
                      {...register(`employment.${index}.currentlyWorking`)}
                      className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-600"
                    />
                    <label htmlFor={`currentWork_${index}`} className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                      I currently work here
                    </label>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {fields.length === 0 && (
          <div className="text-center py-8 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
            No employment history added yet.
          </div>
        )}
      </div>
    </div>
  );
};
