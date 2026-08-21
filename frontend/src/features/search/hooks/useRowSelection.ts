import { useSearchStore } from '../store/searchStore';
import type { OnChangeFn, RowSelectionState } from '@tanstack/react-table';
import { useCallback } from 'react';

export const useRowSelection = () => {
  const selectedRowIds = useSearchStore((state) => state.selectedRowIds);
  const setSelectedRowIds = useSearchStore((state) => state.setSelectedRowIds);

  const handleRowSelectionChange: OnChangeFn<RowSelectionState> = useCallback((updaterOrValue) => {
    const newSelection = typeof updaterOrValue === 'function' ? updaterOrValue(selectedRowIds) : updaterOrValue;
    setSelectedRowIds(newSelection);
  }, [selectedRowIds, setSelectedRowIds]);

  const clearSelection = useCallback(() => {
    setSelectedRowIds({});
  }, [setSelectedRowIds]);

  return {
    rowSelection: selectedRowIds,
    onRowSelectionChange: handleRowSelectionChange,
    clearSelection,
    setSelectedRowIds,  // ← exposed for Quick Select
  };
};