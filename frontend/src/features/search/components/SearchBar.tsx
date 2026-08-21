import { Search, X } from 'lucide-react';
import { useJobSearch } from '../hooks/useJobSearch';

export const SearchBar = () => {
  const { keyword, setKeyword } = useJobSearch();

  return (
    <div className="relative max-w-3xl w-full group mb-6">
      <div className="absolute inset-y-0 left-0 flex items-center pl-4 pointer-events-none text-gray-400 group-focus-within:text-indigo-500 transition-colors">
        <Search className="h-5 w-5" />
      </div>
      <input
        type="text"
        className="block w-full rounded-full border-0 py-4 pl-12 pr-14 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-700 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-lg sm:leading-6 transition-all duration-200 ease-in-out"
        placeholder="Search AI Engineer, Project Manager, Data Scientist..."
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
      />
      {keyword && (
        <button
          onClick={() => setKeyword('')}
          className="absolute inset-y-0 right-0 flex items-center pr-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
        >
          <X className="h-5 w-5" />
        </button>
      )}
    </div>
  );
};
