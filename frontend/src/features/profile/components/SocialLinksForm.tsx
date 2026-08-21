import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const SocialLinksForm = () => {
  const { register, formState: { errors } } = useFormContext<ProfileFormValues>();

  const fields = [
    { name: 'social.linkedin', label: 'LinkedIn', placeholder: 'https://linkedin.com/in/...' },
    { name: 'social.github', label: 'GitHub', placeholder: 'https://github.com/...' },
    { name: 'social.portfolio', label: 'Portfolio Website', placeholder: 'https://...' },
    { name: 'social.twitter', label: 'Twitter', placeholder: 'https://twitter.com/...' },
    { name: 'social.stackOverflow', label: 'StackOverflow', placeholder: 'https://stackoverflow.com/...' },
  ] as const;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-6">Social Links</h3>
      
      <div className="space-y-4">
        {fields.map((field) => (
          <div key={field.name}>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{field.label}</label>
            <input
              type="url"
              {...register(field.name)}
              placeholder={field.placeholder}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {/* @ts-ignore dynamic access */}
            {errors.social?.[field.name.split('.')[1]] && <p className="text-red-500 text-xs mt-1">{errors.social[field.name.split('.')[1]]?.message}</p>}
          </div>
        ))}
      </div>
    </div>
  );
};
