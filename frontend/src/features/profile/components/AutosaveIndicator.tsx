import { motion, AnimatePresence } from 'framer-motion';
import { Save, CheckCircle2, Loader2 } from 'lucide-react';

export type SaveState = 'idle' | 'saving' | 'saved' | 'error';

interface AutosaveIndicatorProps {
  status: SaveState;
}

export const AutosaveIndicator = ({ status }: AutosaveIndicatorProps) => {
  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence mode="wait">
        {status === 'saving' && (
          <motion.div
            key="saving"
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-full shadow-lg font-medium text-sm"
          >
            <Loader2 className="w-4 h-4 animate-spin" />
            Saving changes...
          </motion.div>
        )}
        
        {status === 'saved' && (
          <motion.div
            key="saved"
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="flex items-center gap-2 bg-emerald-600 text-white px-4 py-2.5 rounded-full shadow-lg font-medium text-sm"
          >
            <CheckCircle2 className="w-4 h-4" />
            All changes saved
          </motion.div>
        )}

        {status === 'error' && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="flex items-center gap-2 bg-red-600 text-white px-4 py-2.5 rounded-full shadow-lg font-medium text-sm"
          >
            <Save className="w-4 h-4" />
            Save failed. Retrying...
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
