"""Update checker service"""
import subprocess
import logging
import threading
import time
import os

class UpdateChecker:
    def __init__(self, state, check_interval=3600):
        """
        Initialize update checker
        
        Args:
            state: Application state
            check_interval: Seconds between update checks (default: 1 hour)
        """
        self.state = state
        self.check_interval = check_interval
        self.repo_path = "/home/orangepi/screen-manager"
        self.ansible_repo = "https://github.com/ORION-DEVELOPMENT-DIONE/update-manager.git"
        self.screen_repo = "https://github.com/ORION-DEVELOPMENT-DIONE/screen-manager.git"
        self.current_version = self._get_current_version()
        self.latest_version = None
        self.update_available = False
        self.checking = False
        self.last_check_time = 0
        
        logging.info(f"Update checker initialized for: {self.repo_path}")
        
        # Fix git ownership issues
        self._fix_git_ownership()
        
        # Start background checker
        self.checker_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.checker_thread.start()
    
    def _fix_git_ownership(self):
        """Fix git ownership/permission issues"""
        try:
            # Add to safe directory
            subprocess.run(
                ['git', 'config', '--global', '--add', 'safe.directory', self.repo_path],
                capture_output=True, timeout=5
            )
            
            logging.info("Git ownership fixed")
        except Exception as e:
            logging.debug(f"Could not fix git ownership (non-critical): {e}")
    
    def _get_current_version(self):
        """Get current installed version"""
        version_file = os.path.join(self.repo_path, ".version")
        
        try:
            # Try .version file first
            if os.path.exists(version_file):
                with open(version_file, 'r') as f:
                    version = f.read().strip()
                    if version:
                        logging.info(f"Current version from .version: {version}")
                        return version
            
            # Fallback to git
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # Create .version file for next time
                try:
                    with open(version_file, 'w') as f:
                        f.write(version)
                    logging.info(f"Created .version file with: {version}")
                except:
                    pass
                return version
        except Exception as e:
            logging.error(f"Error getting current version: {e}")
        
        return "unknown"
    
    def _get_remote_version(self):
        """Get latest version from remote repository"""
        try:
            # Fetch latest from remote
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'fetch', 'origin'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                logging.warning(f"Git fetch failed: {result.stderr}")
                return None
            
            # Get current branch
            branch_result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            
            if branch_result.returncode != 0:
                logging.error("Could not determine current branch")
                return None
            
            branch = branch_result.stdout.strip()
            
            # Get remote HEAD hash
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--short', f'origin/{branch}'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
        
        except Exception as e:
            logging.error(f"Error getting remote version: {e}")
        
        return None
    
    def check_for_updates(self):
        """Check if updates are available"""
        if self.checking:
            return False
        
        self.checking = True
        logging.info("Checking for updates...")
        
        try:
            self.latest_version = self._get_remote_version()
            
            if self.latest_version and self.latest_version != self.current_version:
                self.update_available = True
                self.state.update_available = True
                logging.info(f"✅ Update available: {self.current_version} -> {self.latest_version}")
                return True
            else:
                self.update_available = False
                self.state.update_available = False
                logging.info(f"No updates available (current: {self.current_version})")
                return False
        
        finally:
            self.checking = False
            self.last_check_time = time.time()
    
    def _check_loop(self):
        """Background loop to check for updates periodically"""
        # Wait 60 seconds before first check
        time.sleep(60)
        
        while True:
            try:
                if not self.state.is_standby:
                    self.check_for_updates()
            except Exception as e:
                logging.error(f"Update check error: {e}")
            
            time.sleep(self.check_interval)
    
    def perform_update(self):
        """Perform update using git pull (testing mode - no ansible)"""
        logging.info("Starting update process...")
        
        try:
            # Get current branch name first
            branch_result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            
            if branch_result.returncode != 0:
                return (False, "Could not detect branch")
            
            branch = branch_result.stdout.strip()
            logging.info(f"Updating branch: {branch}")
            
            # Stash any local changes
            subprocess.run(
                ['git', '-C', self.repo_path, 'stash'],
                capture_output=True, timeout=10
            )
            
            # Pull latest changes with specific branch
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'pull', 'origin', branch],  # ✅ Add branch
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                logging.info("Update completed successfully")
                logging.info(f"Git output: {result.stdout}")
                
                # Update .version file
                new_version = subprocess.run(
                    ['git', '-C', self.repo_path, 'rev-parse', '--short', 'HEAD'],
                    capture_output=True, text=True, timeout=5
                )
                
                if new_version.returncode == 0:
                    version_file = os.path.join(self.repo_path, ".version")
                    with open(version_file, 'w') as f:
                        f.write(new_version.stdout.strip())
                
                # Refresh current version
                self.current_version = self._get_current_version()
                self.update_available = False
                self.state.update_available = False
                
                return (True, "Update successful!\nRestarting...")
            else:
                logging.error(f"Git pull failed: {result.stderr}")
                return (False, f"Update failed:\n{result.stderr[:100]}")
        
        except subprocess.TimeoutExpired:
            logging.error("Update timed out")
            return (False, "Update timeout")
        except Exception as e:
            logging.error(f"Update error: {e}")
            return (False, f"Error: {str(e)[:50]}")
        
    def get_update_info(self):
        """Get update information for display"""
        return {
            'current': self.current_version,
            'latest': self.latest_version if self.latest_version else 'checking...',
            'available': self.update_available,
            'last_check': self.last_check_time
        }