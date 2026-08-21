import { useState, type KeyboardEvent } from 'react';
import { X, Plus } from 'lucide-react';
import { useFormContext } from 'react-hook-form';
import type { ProfileFormValues } from '../schema';

export const SkillsInput = () => {
  const { watch, setValue } = useFormContext<ProfileFormValues>();
  const [inputValue, setInputValue] = useState('');
  
  const skills = watch('skills') || [];

  const handleAdd = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !skills.includes(trimmed)) {
      setValue('skills', [...skills, trimmed], { shouldDirty: true });
      setInputValue('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  };

  const removeSkill = (skillToRemove: string) => {
    setValue('skills', skills.filter(s => s !== skillToRemove), { shouldDirty: true });
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Skills</h3>
      
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. React, Python, Project Management"
          className="flex-1 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          type="button"
          onClick={handleAdd}
          className="px-4 py-2 bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors flex items-center justify-center"
        >
          <Plus className="w-5 h-5" />
        </button>
      </div>

      <div className="flex flex-wrap gap-2 min-h-[40px]">
        {skills.map((skill) => (
          <span 
            key={skill}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
          >
            {skill}
            <button
              type="button"
              onClick={() => removeSkill(skill)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-100 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </span>
        ))}
        {skills.length === 0 && (
          <span className="text-sm text-gray-400 italic">No skills added yet</span>
        )}
      </div>
    </div>
  );
};
