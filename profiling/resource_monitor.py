import os
import time
import threading
import json
import psutil
from datetime import datetime
from loguru import logger

# Directory for storing resource monitoring results
PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'profiling_results', 'resources')
os.makedirs(PROFILE_DIR, exist_ok=True)

class ResourceMonitor:
    """
    Monitor system resource usage (CPU, memory, disk, network).
    
    This class provides tools for tracking resource usage over time and
    generating reports on resource consumption.
    """
    
    def __init__(self, interval=5.0, log_to_console=False):
        """
        Initialize the resource monitor.
        
        Args:
            interval (float): Sampling interval in seconds
            log_to_console (bool): Whether to log metrics to console
        """
        self.interval = interval
        self.log_to_console = log_to_console
        self.running = False
        self.thread = None
        self.metrics = []
        self.start_time = None
        self.process = psutil.Process(os.getpid())
        
    def start(self):
        """Start resource monitoring in a background thread."""
        if self.running:
            logger.warning("Resource monitor is already running")
            return
            
        self.running = True
        self.start_time = time.time()
        self.metrics = []
        
        # Start monitoring thread
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
        logger.info(f"Resource monitoring started with {self.interval}s interval")
        
    def stop(self):
        """Stop resource monitoring and return collected metrics."""
        if not self.running:
            logger.warning("Resource monitor is not running")
            return self.metrics
            
        self.running = False
        if self.thread:
            self.thread.join(timeout=self.interval + 1)
            
        logger.info(f"Resource monitoring stopped after {time.time() - self.start_time:.1f}s")
        return self.metrics
        
    def _monitor_loop(self):
        """Background thread function to collect resource metrics."""
        while self.running:
            try:
                # Collect metrics
                metrics = self._collect_metrics()
                self.metrics.append(metrics)
                
                if self.log_to_console:
                    logger.info(
                        f"CPU: {metrics['cpu_percent']}%, "
                        f"Memory: {metrics['memory_percent']}% ({metrics['memory_used_mb']:.1f}MB), "
                        f"Disk I/O: {metrics['disk_read_mb']:.1f}MB read, {metrics['disk_write_mb']:.1f}MB write, "
                        f"Network: {metrics['net_sent_mb']:.1f}MB sent, {metrics['net_recv_mb']:.1f}MB recv"
                    )
                    
            except Exception as e:
                logger.error(f"Error collecting resource metrics: {str(e)}")
                
            # Sleep until next collection
            time.sleep(self.interval)
            
    def _collect_metrics(self):
        """
        Collect current resource usage metrics.
        
        Returns:
            dict: Dictionary of resource metrics
        """
        # Get process info - исправляем список атрибутов
        try:
            process_info = self.process.as_dict(attrs=[
                'cpu_percent', 'memory_percent', 'memory_info',
                'io_counters'
            ])
            
            # Получаем connections отдельно, так как он может вызывать ошибки
            try:
                process_connections = len(self.process.connections())
            except (psutil.AccessDenied, AttributeError):
                process_connections = 0
        except Exception as e:
            logger.error(f"Error getting process info: {str(e)}")
            process_info = {}
            process_connections = 0
        
        # Get system info
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            cpu_percent = 0
            memory = psutil._common.sdiskio(total=0, used=0, free=0, percent=0)
            disk_io = None
            net_io = None
        
        # Безопасно получаем количество открытых файлов
        try:
            open_files_count = len(self.process.open_files())
        except (psutil.AccessDenied, AttributeError):
            open_files_count = 0
        
        # Безопасно получаем количество потоков
        try:
            threads_count = self.process.num_threads()
        except (psutil.AccessDenied, AttributeError):
            threads_count = 0
        
        # Build metrics dictionary
        metrics = {
            'timestamp': time.time(),
            'elapsed': time.time() - self.start_time,
            
            # Process metrics
            'process_cpu_percent': process_info.get('cpu_percent', 0),
            'process_memory_percent': process_info.get('memory_percent', 0),
            'process_memory_rss_mb': process_info.get('memory_info', {}).rss / (1024 * 1024) if process_info.get('memory_info') else 0,
            'process_open_files': open_files_count,
            'process_threads': threads_count,
            'process_connections': process_connections,
            
            # System metrics
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent if hasattr(memory, 'percent') else 0,
            'memory_used_mb': memory.used / (1024 * 1024) if hasattr(memory, 'used') else 0,
            'memory_available_mb': memory.available / (1024 * 1024) if hasattr(memory, 'available') else 0,
            'disk_read_mb': disk_io.read_bytes / (1024 * 1024) if disk_io and hasattr(disk_io, 'read_bytes') else 0,
            'disk_write_mb': disk_io.write_bytes / (1024 * 1024) if disk_io and hasattr(disk_io, 'write_bytes') else 0,
            'net_sent_mb': net_io.bytes_sent / (1024 * 1024) if net_io and hasattr(net_io, 'bytes_sent') else 0,
            'net_recv_mb': net_io.bytes_recv / (1024 * 1024) if net_io and hasattr(net_io, 'bytes_recv') else 0
        }
        
        return metrics
        
    def save_metrics_to_file(self):
        """
        Save collected metrics to a file.
        
        Returns:
            str: Path to the saved file
        """
        if not self.metrics:
            logger.warning("No metrics to save")
            return None
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(PROFILE_DIR, f"resource_metrics_{timestamp}.json")
        
        with open(filename, 'w') as f:
            json.dump({
                'start_time': self.start_time,
                'interval': self.interval,
                'metrics': self.metrics
            }, f, indent=2)
            
        logger.info(f"Resource metrics saved to {filename}")
        return filename
        
    def get_summary(self):
        """
        Generate a summary of resource usage.
        
        Returns:
            dict: Summary statistics
        """
        if not self.metrics:
            return {"error": "No metrics collected"}
            
        # Calculate summary statistics
        summary = {
            'duration': time.time() - self.start_time if self.start_time else 0,
            'samples': len(self.metrics),
            'cpu': {
                'min': min(m['cpu_percent'] for m in self.metrics),
                'max': max(m['cpu_percent'] for m in self.metrics),
                'avg': sum(m['cpu_percent'] for m in self.metrics) / len(self.metrics)
            },
            'memory': {
                'min_percent': min(m['memory_percent'] for m in self.metrics),
                'max_percent': max(m['memory_percent'] for m in self.metrics),
                'avg_percent': sum(m['memory_percent'] for m in self.metrics) / len(self.metrics),
                'min_mb': min(m['memory_used_mb'] for m in self.metrics),
                'max_mb': max(m['memory_used_mb'] for m in self.metrics),
                'avg_mb': sum(m['memory_used_mb'] for m in self.metrics) / len(self.metrics)
            },
            'process': {
                'min_cpu': min(m['process_cpu_percent'] for m in self.metrics),
                'max_cpu': max(m['process_cpu_percent'] for m in self.metrics),
                'avg_cpu': sum(m['process_cpu_percent'] for m in self.metrics) / len(self.metrics),
                'min_memory': min(m['process_memory_percent'] for m in self.metrics),
                'max_memory': max(m['process_memory_percent'] for m in self.metrics),
                'avg_memory': sum(m['process_memory_percent'] for m in self.metrics) / len(self.metrics)
            }
        }
        
        return summary


# Singleton instance for application-wide monitoring
_monitor = None

def start_resource_monitoring(interval=5.0, log_to_console=False):
    """
    Start monitoring system resources.
    
    Args:
        interval (float): Sampling interval in seconds
        log_to_console (bool): Whether to log metrics to console
        
    Returns:
        ResourceMonitor: The monitor instance
    """
    global _monitor
    
    if _monitor is None:
        _monitor = ResourceMonitor(interval=interval, log_to_console=log_to_console)
        
    if not _monitor.running:
        _monitor.start()
        
    return _monitor
    
def stop_resource_monitoring():
    """
    Stop resource monitoring and save results.
    
    Returns:
        str: Path to the saved metrics file, or None if no metrics
    """
    global _monitor
    
    if _monitor is None or not _monitor.running:
        logger.warning("Resource monitoring is not running")
        return None
        
    metrics = _monitor.stop()
    if metrics:
        return _monitor.save_metrics_to_file()
    return None
    
def get_resource_metrics_summary():
    """
    Get a summary of resource usage metrics.
    
    Returns:
        dict: Summary statistics, or None if monitoring is not active
    """
    global _monitor
    
    if _monitor is None:
        return None
        
    return _monitor.get_summary()