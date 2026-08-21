import { useSearchStore } from '../store/searchStore';

export const usePagination = () => {
  const page = useSearchStore((state) => state.page);
  const limit = useSearchStore((state) => state.limit);
  const setPage = useSearchStore((state) => state.setPage);
  const setLimit = useSearchStore((state) => state.setLimit);

  return { page, limit, setPage, setLimit };
};
