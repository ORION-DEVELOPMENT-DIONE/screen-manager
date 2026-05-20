"""Energy data analysis service"""
import time
import json
import os
from datetime import datetime, timedelta
from collections import deque
import logging

class EnergyAnalyzer:
    def __init__(self, log_file="../logs/mqtt_data_log.txt"):
        self.log_file = log_file
        self.data_24h = deque(maxlen=288)  # Last 24 hours (5 min intervals)
        self.data_7d = deque(maxlen=336)   # Last 7 days (30 min intervals)
        self.last_data_time = None
        self.last_5min_save = 0
        self.last_30min_save = 0
        
        # Load historical data from log file
        self._load_historical_data()
    
    def _load_historical_data(self):
        """Load historical data from log file"""
        if not os.path.exists(self.log_file):
            logging.info("No log file found, starting fresh")
            return
        
        try:
            now = time.time()
            cutoff_24h = now - (24 * 3600)  # 24 hours ago
            cutoff_7d = now - (7 * 24 * 3600)  # 7 days ago
            
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            
            # Process lines in reverse (newest first) for efficiency
            for line in reversed(lines[-1000:]):  # Only check last 1000 lines
                try:
                    # Parse line: "2026-02-05 19:50:26 - {json data}"
                    if ' - {' not in line:
                        continue
                    
                    timestamp_str, json_str = line.split(' - ', 1)
                    data = json.loads(json_str.strip())
                    
                    # Parse timestamp
                    dt = datetime.strptime(timestamp_str.strip(), "%Y-%m-%d %H:%M:%S")
                    timestamp = dt.timestamp()
                    
                    # Skip old data
                    if timestamp < cutoff_7d:
                        break  # Since we're going in reverse, we can stop
                    
                    # Add to 24h data
                    if timestamp >= cutoff_24h:
                        self.data_24h.appendleft({
                            'timestamp': timestamp,
                            'battery': data.get('battery', 0),                            
                            'voltage': data.get('voltage', 0),
                            'totalPower': data.get('totalPower', 0),
                            'energyTotal': data.get('energyTotal', 0),
                            'phases': data.get('phases', [])
                        })
                    
                    # Add to 7d data (sample every ~30 min)
                    self.data_7d.appendleft({
                        'timestamp': timestamp,
                        'battery': data.get('battery', 0),
                        'voltage': data.get('voltage', 0),
                        'totalPower': data.get('totalPower', 0),
                        'energyTotal': data.get('energyTotal', 0)
                    })
                
                except Exception as e:
                    logging.debug(f"Error parsing log line: {e}")
                    continue
            
            # Reverse to get chronological order
            self.data_24h.reverse()
            self.data_7d.reverse()
            
            logging.debug(f"Loaded {len(self.data_24h)} 24h samples and {len(self.data_7d)} 7d samples")
        
        except Exception as e:
            logging.error(f"Error loading historical data: {e}")
    
    def add_data_point(self, data):
        """Add new data point and manage history"""
        current_time = time.time()
        
        # Always update last data time
        self.last_data_time = current_time
        
        # Save to 24h history (every 5 minutes)
        if current_time - self.last_5min_save >= 300:  # 5 minutes
            self.data_24h.append({
                'timestamp': current_time,
                'battery': data.get('battery', 0),
                'voltage': data.get('voltage', 0),
                'totalPower': data.get('totalPower', 0),
                'energyTotal': data.get('energyTotal', 0),
                'phases': data.get('phases', [])
            })
            self.last_5min_save = current_time
        
        # Save to 7d history (every 30 minutes)
        if current_time - self.last_30min_save >= 1800:  # 30 minutes
            self.data_7d.append({
                'timestamp': current_time,
                'battery': data.get('battery', 0),
                'voltage': data.get('voltage', 0),
                'totalPower': data.get('totalPower', 0),
                'energyTotal': data.get('energyTotal', 0)
            })
            self.last_30min_save = current_time
    
    def get_time_since_last_data(self):
        """Get formatted time since last data received"""
        if not self.last_data_time:
            return "No data yet"
        
        elapsed = time.time() - self.last_data_time
        
        if elapsed < 60:
            return f"{int(elapsed)}s ago"
        elif elapsed < 3600:
            return f"{int(elapsed/60)}min ago"
        elif elapsed < 86400:
            hours = int(elapsed/3600)
            mins = int((elapsed % 3600)/60)
            return f"{hours}h {mins}min ago"
        else:
            days = int(elapsed/86400)
            return f"{days}d ago"
    
    def get_24h_stats(self):
        """Get statistics for last 24 hours"""
        if not self.data_24h:
            return None
        
        powers = [d['totalPower'] for d in self.data_24h if d['totalPower'] > 0]
        energies = [d['energyTotal'] for d in self.data_24h]
        
        if not powers:
            return None
        
        return {
            'avg_power': sum(powers) / len(powers),
            'max_power': max(powers),
            'min_power': min(powers),
            'total_energy': energies[-1] - energies[0] if len(energies) > 1 else 0,
            'data_points': len(self.data_24h)
        }
    
    def get_7d_stats(self):
        """Get statistics for last 7 days"""
        if not self.data_7d:
            return None
        
        powers = [d['totalPower'] for d in self.data_7d if d['totalPower'] > 0]
        energies = [d['energyTotal'] for d in self.data_7d]
        
        if not powers:
            return None
        
        return {
            'avg_power': sum(powers) / len(powers),
            'max_power': max(powers),
            'min_power': min(powers),
            'total_energy': energies[-1] - energies[0] if len(energies) > 1 else 0,
            'data_points': len(self.data_7d)
        }
    
    def get_chart_data_24h(self):
        """Get data formatted for 24h chart"""
        return list(self.data_24h)
    
    def get_chart_data_7d(self):
        """Get data formatted for 7d chart"""
        return list(self.data_7d)