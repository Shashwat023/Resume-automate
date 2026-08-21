import { motion } from 'framer-motion';
import { useProfileStore } from '../../../store/profileStore';
import { AlertCircle, CheckCircle2 } from 'lucide-react';

export const ProfileCompletion = () => {
  const profile = useProfileStore((state) => state.profile);

  // Basic calculation logic
  const calculateCompletion = () => {
    let score = 0;
    const total = 10;
    const missing: string[] = [];

    if (profile?.personal?.firstName && profile?.personal?.lastName) score++;
    else missing.push('Name');

    if (profile?.contact?.email && profile?.contact?.phone) score++;
    else missing.push('Contact Details');

    if (profile?.contact?.fullAddress) score++;
    else missing.push('Address');

    if (profile?.professional?.currentJobTitle) score++;
    else missing.push('Current Role');

    if (profile?.education && profile.education.length > 0) score++;
    else missing.push('Education');

    if (profile?.employment && profile.employment.length > 0) score++;
    else missing.push('Experience');

    if (profile?.social?.linkedin) score++;
    else missing.push('LinkedIn Profile');

    if (profile?.skills && profile.skills.length >= 3) score++;
    else missing.push('3+ Skills');

    if (profile?.preferences?.preferredRoles && profile.preferences.preferredRoles.length > 0) score++;
    else missing.push('Job Preferences');

    if (profile?.summary && profile.summary.length > 10) score++;
    else missing.push('Professional Summary');

    const percentage = Math.round((score / total) * 100);
    return { percentage, missing };
  };

  const { percentage, missing } = calculateCompletion();
  const isComplete = percentage === 100;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-200 dark:border-gray-700 shadow-sm h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">Profile Completeness</h3>
        <span className={`text-sm font-bold ${isComplete ? 'text-emerald-600 dark:text-emerald-400' : 'text-indigo-600 dark:text-indigo-400'}`}>
          {percentage}%
        </span>
      </div>

      <div className="relative h-2 w-full bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden mb-6">
        <motion.div 
          className={`absolute top-0 left-0 h-full rounded-full ${isComplete ? 'bg-emerald-500' : 'bg-indigo-600'}`}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, delay: 0.2 }}
        />
      </div>

      {isComplete ? (
        <div className="flex items-start gap-3 bg-emerald-50 dark:bg-emerald-900/20 p-4 rounded-xl border border-emerald-100 dark:border-emerald-900/30">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-emerald-900 dark:text-emerald-200">Excellent!</p>
            <p className="text-xs text-emerald-700 dark:text-emerald-400 mt-1">Your profile is fully optimized for ATS auto-applications.</p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Missing fields to optimize ATS match:</p>
          <ul className="space-y-2">
            {missing.slice(0, 4).map((item, idx) => (
              <li key={idx} className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" />
                {item}
              </li>
            ))}
            {missing.length > 4 && (
              <li className="text-xs text-gray-400 dark:text-gray-500 italic ml-6">
                + {missing.length - 4} more items
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
};
