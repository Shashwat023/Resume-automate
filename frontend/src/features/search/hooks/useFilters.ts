import { useSearchStore } from '../store/searchStore';

export const useFilters = () => {
  const filters = useSearchStore((state) => state.filters);
  const setFilters = useSearchStore((state) => state.setFilters);
  const resetFilters = useSearchStore((state) => state.resetFilters);

  return { filters, setFilters, resetFilters };
};
