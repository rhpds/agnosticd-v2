#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    callback: reload_collections
    callback_type: notification
    requirements:
      - python >= 3.5
    short_description: Reloads collection paths after specific tasks
    description:
      - This callback plugin reloads Ansible collection paths after a specific task marker
      - Add a task with the tag 'reload_collections' to trigger the reload
    options:
      marker_task:
        default: "Collections installed"
        description: Task name that signals collections have been installed
        env:
          - name: RELOAD_COLLECTIONS_MARKER
        ini:
          - section: callback_reload_collections
            key: marker_task
'''

import os
import sys
import importlib
import ansible.plugins.loader as plugin_loader
from ansible.plugins.callback import CallbackBase

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'reload_collections'
    CALLBACK_NEEDS_WHITELIST = False

    def __init__(self):
        super(CallbackModule, self).__init__()
        self.marker_task = "Collections installed"
        self.collection_reload_needed = False
        self._display.display(">>> COLLECTION RELOADER PLUGIN INITIALIZED <<<", color='green')

        # Create debug file
        with open('/tmp/collection_reloader_debug.log', 'w') as f:
            f.write('Plugin initialized\n')

    def v2_playbook_on_task_start(self, task, is_conditional):
        task_name = task.get_name()

        # Log the task name for debugging
        with open('/tmp/collection_reloader_debug.log', 'a') as f:
            f.write(f'Task started: {task_name}\n')

        # Check for reload marker
        if task_name == self.marker_task or 'reload_collections' in task.tags:
            self._display.display(f">>> COLLECTION RELOAD MARKER TASK DETECTED: {task_name} <<<", color='yellow')
            self.collection_reload_needed = True

    def v2_runner_on_ok(self, result):
        task_name = result._task.get_name()

        # Check if it's a collection install task or our marker task
        if self.collection_reload_needed:
            self._display.display(f">>> Checking result for task: {task_name} <<<", color='blue')

            # Check if result contains ansible-galaxy collection install or if it's our marker task
            result_str = str(result._result)
            if 'ansible-galaxy collection install' in result_str or 'galaxy' in result_str or task_name == self.marker_task:
                self._display.display(">>> COLLECTION INSTALLATION DETECTED <<<", color='yellow')
                self.reload_collection_paths()
                self.collection_reload_needed = False

    def reload_collection_paths(self):
        """Reload Ansible collection paths to make newly installed collections available"""
        self._display.display(">>> RELOADING COLLECTION PATHS... <<<", color='red')

        try:
            # Method 1: Try to reset collection cache using AnsibleCollectionConfig
            self._display.display("Trying method 1: Reset using AnsibleCollectionConfig")
            try:
                from ansible.utils.collection_loader import AnsibleCollectionConfig
                AnsibleCollectionConfig.on_collection_load.cache_clear()
                self._display.display(">>> Successfully cleared collection config cache <<<", color='green')
            except (ImportError, AttributeError) as e:
                self._display.display(f"Method 1 failed: {str(e)}", color='yellow')

            # Method 2: Try to use _reset method if available
            self._display.display("Trying method 2: Reset using module_loader._reset")
            try:
                if hasattr(plugin_loader.module_loader, '_reset'):
                    plugin_loader.module_loader._reset()
                    self._display.display(">>> Successfully reset module_loader <<<", color='green')
            except AttributeError as e:
                self._display.display(f"Method 2 failed: {str(e)}", color='yellow')

            # Method 3: Try to use _return_first_found_default_value
            self._display.display("Trying method 3: Reset first found defaults")
            try:
                if hasattr(plugin_loader.module_loader, '_return_first_found_default_value'):
                    setattr(plugin_loader.module_loader, '_return_first_found_default_value', {})
                    self._display.display(">>> Successfully reset _return_first_found_default_value <<<", color='green')
            except AttributeError as e:
                self._display.display(f"Method 3 failed: {str(e)}", color='yellow')

            # Method 4: Force reimport of collection loader
            self._display.display("Trying method 4: Reload collection loader modules")
            try:
                if 'ansible.utils.collection_loader' in sys.modules:
                    importlib.reload(sys.modules['ansible.utils.collection_loader'])
                    self._display.display(">>> Successfully reloaded collection_loader module <<<", color='green')

                if 'ansible.utils.collection_loader._collection_finder' in sys.modules:
                    importlib.reload(sys.modules['ansible.utils.collection_loader._collection_finder'])
                    self._display.display(">>> Successfully reloaded _collection_finder module <<<", color='green')
            except Exception as e:
                self._display.display(f"Method 4 failed: {str(e)}", color='yellow')

            # Method 5: Try to reload collection paths directly
            self._display.display("Trying method 5: Reinstall collection finder")
            try:
                from ansible.utils.collection_loader._collection_finder import _AnsibleCollectionFinder
                if hasattr(_AnsibleCollectionFinder, '_install'):
                    _AnsibleCollectionFinder._install()
                    self._display.display(">>> Successfully reinstalled collection finder <<<", color='green')
            except Exception as e:
                self._display.display(f"Method 5 failed: {str(e)}", color='yellow')

            # Log success message
            self._display.display(">>> Completed collection path reload attempts <<<", color='green')
            self._display.display(">>> You may need to re-import collections in your playbook <<<", color='yellow')

        except Exception as e:
            error_msg = f"Failed during reload collection paths: {str(e)}"
            self._display.error(error_msg)
