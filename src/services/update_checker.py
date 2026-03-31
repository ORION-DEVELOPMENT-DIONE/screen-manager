"""Update checker service"""
import subprocess
import logging
import threading
import time
import os
import urllib.request

_FALLBACK_DESCRIPTION = "• A new version of Orion is ready to install."


class UpdateChecker:
    def __init__(self, state, check_interval=3600):
        self.state          = state
        self.check_interval = check_interval

        if os.path.exists("/home/orangepi/screen-manager"):
            self.repo_path = "/home/orangepi/screen-manager"
        elif os.path.exists("/home/orangepi/screen-manager2"):
            self.repo_path = "/home/orangepi/screen-manager2"
        else:
            self.repo_path = "/home/orangepi/screen-manager"

        self.ansible_repo   = "https://github.com/ORION-DEVELOPMENT-DIONE/update-manager.git"
        self.screen_repo    = "https://github.com/ORION-DEVELOPMENT-DIONE/screen-manager"
        self._changelog_url = (
            "https://raw.githubusercontent.com/"
            "ORION-DEVELOPMENT-DIONE/screen-manager/main/CHANGELOG.md"
        )

        self.current_version    = self._get_current_version()
        self.latest_version     = None
        self.update_available   = False
        self.update_description = _FALLBACK_DESCRIPTION  # read by UpdateMenu
        self.checking           = False
        self.last_check_time    = 0

        logging.info(f"Update checker initialized for: {self.repo_path}")
        self._fix_git_ownership()

        self.checker_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.checker_thread.start()
        # TESTING — force update state with local CHANGELOG.md
        import pathlib
        changelog = self._get_local_changelog()
        self.update_description = self._parse_changelog(changelog, "edd261a")
        self.update_available = True
        self.state.update_available = True
        self.latest_version = "edd261a"

    # ── git helpers ───────────────────────────────────────────────────────────
    
    def _fix_git_ownership(self):
        try:
            subprocess.run(
                ['git', 'config', '--global', '--add', 'safe.directory', self.repo_path],
                capture_output=True, timeout=5
            )
            subprocess.run(
                ['chown', '-R', 'orangepi:orangepi', self.repo_path],
                capture_output=True, timeout=10
            )
            logging.info("Git ownership fixed")
        except Exception as e:
            logging.debug(f"Could not fix git ownership (non-critical): {e}")

    def _get_current_version(self):
        try:
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logging.info(f"Current version: {version}")
                return version
            logging.error("Could not get current git commit")
            return "unknown"
        except Exception as e:
            logging.error(f"Error getting current version: {e}")
            return "unknown"

    def _get_remote_version(self):
        try:
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'fetch', 'origin'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                logging.warning(f"Git fetch failed: {result.stderr}")
                return None

            branch_result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if branch_result.returncode != 0:
                return None

            branch = branch_result.stdout.strip()
            result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--short', f'origin/{branch}'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logging.error(f"Error getting remote version: {e}")
        return None

    # ── changelog ─────────────────────────────────────────────────────────────

    def _get_remote_changelog(self):
        try:
            req = urllib.request.Request(
                self._changelog_url,
                headers={"User-Agent": "OrionUpdateChecker/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            logging.warning(f"Could not fetch CHANGELOG.md: {e}")
            return None

    def _get_local_changelog(self):
        """Read CHANGELOG.md from local repo (fallback / for testing)."""
        import pathlib
        try:
            return (pathlib.Path(self.repo_path) / "CHANGELOG.md").read_text()
        except Exception as e:
            logging.warning(f"Could not read local CHANGELOG.md: {e}")
            return None

    def _parse_changelog(self, changelog_text: str, target_hash: str) -> str:
        if not changelog_text:
            return _FALLBACK_DESCRIPTION

        lines, entries, current = changelog_text.splitlines(), {}, None
        for line in lines:
            if line.startswith("## "):
                current = line[3:].strip()
                entries[current] = []
            elif current is not None:
                entries[current].append(line)

        if target_hash in entries:
            return "\n".join(entries[target_hash]).strip()
        for key in entries:
            if key.startswith(target_hash) or target_hash.startswith(key):
                return "\n".join(entries[key]).strip()
        if entries:
            logging.warning(f"Hash '{target_hash}' not in CHANGELOG — showing latest entry")
            return "\n".join(next(iter(entries.values()))).strip()

        return _FALLBACK_DESCRIPTION

    # ── public ────────────────────────────────────────────────────────────────

    def check_for_updates(self):
        if self.checking:
            return False
        self.checking = True
        logging.info("Checking for updates...")
        try:
            self.latest_version = self._get_remote_version()
            if self.latest_version and self.latest_version != self.current_version:
                self.update_available       = True
                self.state.update_available = True
                logging.info(f"Update available: {self.current_version} → {self.latest_version}")
                changelog = self._get_remote_changelog() or self._get_local_changelog()
                self.update_description = self._parse_changelog(changelog, self.latest_version)
                return True
            else:
                self.update_available       = False
                self.state.update_available = False
                logging.info(f"No updates available (current: {self.current_version})")
                return False
        finally:
            self.checking        = False
            self.last_check_time = time.time()

    def _check_loop(self):
        time.sleep(60)
        while True:
            try:
                if not self.state.is_standby:
                    self.check_for_updates()
            except Exception as e:
                logging.error(f"Update check error: {e}")
            time.sleep(self.check_interval)

    def perform_update(self):
        logging.info("Starting update process...")
        try:
            branch_result = subprocess.run(
                ['git', '-C', self.repo_path, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=5
            )
            if branch_result.returncode != 0:
                return (False, "Could not detect branch")

            branch = branch_result.stdout.strip()
            logging.info(f"Updating branch: {branch}")
            subprocess.run(['git', '-C', self.repo_path, 'stash'],
                           capture_output=True, timeout=10)

            result = subprocess.run(
                ['git', '-C', self.repo_path, 'pull', 'origin', branch],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                logging.info("Update completed successfully")
                try:
                    subprocess.run(['chown', '-R', 'orangepi:orangepi', self.repo_path],
                                   capture_output=True, timeout=10)
                except Exception as e:
                    logging.warning(f"Could not fix ownership: {e}")
                self.current_version        = self._get_current_version()
                self.update_available       = False
                self.state.update_available = False
                return (True, "Update successful!\nRestarting...")
            else:
                logging.error(f"Git pull failed: {result.stderr}")
                return (False, "Update failed")
        except subprocess.TimeoutExpired:
            return (False, "Update timeout")
        except Exception as e:
            logging.error(f"Update error: {e}")
            return (False, f"Error: {str(e)[:50]}")

    def get_update_info(self):
        return {
            'current':     self.current_version,
            'latest':      self.latest_version if self.latest_version else 'checking...',
            'available':   self.update_available,
            'description': self.update_description,
            'last_check':  self.last_check_time,
        }