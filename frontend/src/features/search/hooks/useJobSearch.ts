import { useSearchStore } from '../store/searchStore';

export const useJobSearch = () => {
  const keyword = useSearchStore((state) => state.keyword);
  const setKeyword = useSearchStore((state) => state.setKeyword);

  return { keyword, setKeyword };
};