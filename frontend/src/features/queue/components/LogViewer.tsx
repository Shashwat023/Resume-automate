import { useEffect, useRef, useState } from 'react';
import { useQueueStore } from '../../../store/queueStore';
import { Terminal, Download, Search, Maximize2 } from 'lucide-react';
import { clsx } from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

const EMPTY_LOGS: any[] = [];

export const LogViewer = () => {
  const logs = useQueueStore((state) => state.queueState?.logs || EMPTY_LOGS);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll logic
  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Handle manual scroll to pause auto-scroll
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 50;
    setAutoScroll(isAtBottom);
  };

  const filteredLogs = logs.filter(log => 
    log.message.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleDownload = () => {
    const text = logs.map(l => `[${l.timestamp}] [${l.type.toUpperCase()}] ${l.message}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "automation_logs.txt");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-[#1E1E1E] dark:bg-[#121212] rounded-xl border border-gray-800 shadow-xl overflow-hidden flex flex-col h-[400px] lg:h-full min-h-[400px]">
      
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-[#252526] dark:bg-[#1A1A1A] border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-gray-400" />
          <span className="text-xs font-medium text-gray-300 font-mono">automation-bot.log</span>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-500 absolute left-2 top-1/2 transform -translate-y-1/2" />
            <input 
              type="text" 
              placeholder="Filter..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#333333] border-none text-xs text-gray-200 rounded px-2 py-1 pl-7 w-32 focus:ring-1 focus:ring-indigo-500 outline-none font-mono"
            />
          </div>
          <button 
            onClick={handleDownload}
            className="text-gray-400 hover:text-white transition-colors"
            title="Download Logs"
          >
            <Download className="w-4 h-4" />
          </button>
          <button className="text-gray-400 hover:text-white transition-colors">
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Log Output Area */}
      <div 
        className="p-4 flex-1 overflow-y-auto font-mono text-xs sm:text-sm custom-scrollbar bg-[#1E1E1E] dark:bg-[#121212]"
        onScroll={handleScroll}
      >
        <AnimatePresence initial={false}>
          {filteredLogs.map((log) => (
            <motion.div 
              key={log.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className="mb-1.5 break-words flex gap-3 hover:bg-[#2A2A2A] px-1 rounded transition-colors"
            >
              <span className="text-gray-500 shrink-0 select-none">
                {log.timestamp.split('T')[1]?.substring(0, 8) || log.timestamp}
              </span>
              <span className={clsx(
                "flex-1",
                log.type === 'error' ? 'text-red-400' :
                log.type === 'success' ? 'text-emerald-400' :
                log.type === 'warning' ? 'text-amber-400' :
                'text-gray-300'
              )}>
                {log.type === 'error' ? '[ERROR] ' : log.type === 'warning' ? '[WARN] ' : ''}
                {log.message}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {filteredLogs.length === 0 && (
          <div className="text-gray-600 italic">No logs matched your search.</div>
        )}
        
        <div ref={logsEndRef} />
      </div>
      
      {!autoScroll && (
        <div className="absolute bottom-6 right-6">
          <button 
            onClick={() => setAutoScroll(true)}
            className="bg-gray-800/80 text-white text-xs px-3 py-1.5 rounded-full shadow border border-gray-700 backdrop-blur-sm hover:bg-gray-700"
          >
            Resume Auto-scroll
          </button>
        </div>
      )}
    </div>
  );
};
