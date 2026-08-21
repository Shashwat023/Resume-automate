import { useFilters } from '../hooks/useFilters';
import { Filter, MapPin, Briefcase, Server, RotateCcw, Clock, Building2 } from 'lucide-react';

export const FilterPanel = () => {
  const { filters, setFilters, resetFilters } = useFilters();

  const handleFilterChange = (key: keyof typeof filters, value: string) => {
    setFilters({ ...filters, [key]: value });
  };

  const hasActiveFilters = Object.entries(filters).some(([key, val]) => {
    if (key === 'jobType' || key === 'ats' || key === 'timeline' || key === 'industry') return val !== 'All';
    return val !== '';
  });

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4 mb-8">
      <div className="flex flex-col md:flex-row gap-4 items-end">
        
        {/* Job Type */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <Filter className="w-4 h-4" /> Job Type
          </label>
          <select
            value={filters.jobType}
            onChange={(e) => handleFilterChange('jobType', e.target.value)}
            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          >
            <option value="All">All</option>
            <option value="Remote">Remote</option>
            <option value="Hybrid">Hybrid</option>
            <option value="Onsite">Onsite</option>
          </select>
        </div>

        {/* Location */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <MapPin className="w-4 h-4" /> Location
          </label>
          <input
            type="text"
            placeholder="e.g. San Francisco, US"
            value={filters.location}
            onChange={(e) => handleFilterChange('location', e.target.value)}
            className="mt-1 block w-full pl-3 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:bg-white dark:focus:bg-gray-800 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          />
        </div>

        {/* Company */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <Briefcase className="w-4 h-4" /> Company
          </label>
          <input
            type="text"
            placeholder="Search company..."
            value={filters.company}
            onChange={(e) => handleFilterChange('company', e.target.value)}
            className="mt-1 block w-full pl-3 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:bg-white dark:focus:bg-gray-800 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          />
        </div>

        {/* ATS */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <Server className="w-4 h-4" /> ATS
          </label>
          <select
            value={filters.ats}
            onChange={(e) => handleFilterChange('ats', e.target.value)}
            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          >
            <option value="All">All</option>
            <option value="Greenhouse">Greenhouse</option>
            <option value="Lever">Lever</option>
            <option value="Workday">Workday</option>
            <option value="Ashby">Ashby</option>
            <option value="SmartRecruiters">SmartRecruiters</option>
            <option value="Others">Others</option>
          </select>
        </div>

        {/* Timeline */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <Clock className="w-4 h-4" /> Posted Within
          </label>
          <select
            value={filters.timeline}
            onChange={(e) => handleFilterChange('timeline', e.target.value)}
            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          >
            <option value="All">All</option>
            <option value="24h">Last 24 hours</option>
            <option value="week">Last week</option>
            <option value="month">Last month</option>
          </select>
        </div>

        {/* Industry */}
        <div className="flex-1 w-full">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-2">
            <Building2 className="w-4 h-4" /> Industry
          </label>
          <input
            type="text"
            placeholder="e.g. IT, Construction, Healthcare..."
            value={filters.industry === 'All' ? '' : filters.industry}
            onChange={(e) => handleFilterChange('industry', e.target.value || 'All')}
            className="mt-1 block w-full pl-3 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:bg-white dark:focus:bg-gray-800 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          />
        </div>
        
        {/* Clear Filters */}
        <div className="flex-none w-full md:w-auto mt-4 md:mt-0">
          <button
            onClick={resetFilters}
            disabled={!hasActiveFilters}
            className={`w-full flex items-center justify-center gap-2 px-4 py-2 border rounded-md shadow-sm text-sm font-medium transition-colors ${
              hasActiveFilters 
                ? 'border-gray-300 text-gray-700 bg-white hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700' 
                : 'border-transparent text-gray-400 bg-gray-100 dark:bg-gray-800/50 cursor-not-allowed'
            }`}
          >
            <RotateCcw className="w-4 h-4" />
            Clear
          </button>
        </div>

      </div>
    </div>
  );
};
