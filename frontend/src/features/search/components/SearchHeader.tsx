import { motion } from 'framer-motion';

export const SearchHeader = () => {
  return (
    <motion.div
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="mb-8"
    >
      <h1 className="text-3xl font-extrabold tracking-tight text-gray-900 dark:text-gray-100 sm:text-4xl">
        Search Jobs
      </h1>
      <p className="mt-2 text-lg text-gray-500 dark:text-gray-400 max-w-2xl">
        Find, filter, and queue up the best opportunities for auto-application.
        Leave the boring parts to us.
      </p>
    </motion.div>
  );
};
