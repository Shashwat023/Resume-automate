import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface SearchFilters {
  jobType: string;
  location: string;
  company: string;
  ats: string;
  timeline: string;
  industry: string;
}

interface SearchState {
  keyword: string;
  filters: SearchFilters;
  page: number;
  limit: number;
  selectedRowIds: Record<string, boolean>;
  setKeyword: (keyword: string) => void;
  setFilters: (filters: SearchFilters) => void;
  setPage: (page: number) => void;
  setLimit: (limit: number) => void;
  setSelectedRowIds: (ids: Record<string, boolean>) => void;
  resetFilters: () => void;
}

const initialFilters: SearchFilters = {
  jobType: 'All',
  location: '',
  company: '',
  ats: 'All',
  timeline: 'All',
  industry: 'All',
};

export const useSearchStore = create<SearchState>()(
  persist(
    (set) => ({
      keyword: '',
      filters: initialFilters,
      page: 1,
      limit: 10,
      selectedRowIds: {},
      setKeyword: (keyword) => set({ keyword }),
      setFilters: (filters) => set({ filters, page: 1 }), // reset page on filter change
      setPage: (page) => set({ page }),
      setLimit: (limit) => set({ limit, page: 1 }),
      setSelectedRowIds: (selectedRowIds) => set({ selectedRowIds }),
      resetFilters: () => set({ filters: initialFilters, keyword: '', page: 1 }),
    }),
    {
      name: 'auto-apply-search-state',
    }
  )
);
