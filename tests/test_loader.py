# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import tempfile
import shutil
import os
import pytest
from pkg.evaluator.loader import load_from_tasks_dir

def test_load_from_tasks_dir_recursive():
    # Create a temporary directory structure mimicking tasks
    tmpdir = tempfile.mkdtemp()
    try:
        gcp_dir = os.path.join(tmpdir, "gcp", "task-gcp")
        generic_dir = os.path.join(tmpdir, "generic", "task-generic")
        os.makedirs(gcp_dir)
        os.makedirs(generic_dir)
        
        # Write task.yaml files
        task_gcp_content = """
task_id: 1
name: "task-gcp"
prompt: "GCP Prompt"
expected_output: "GCP Expected"
"""
        task_generic_content = """
task_id: 2
name: "task-generic"
prompt: "Generic Prompt"
expected_output: "Generic Expected"
"""
        with open(os.path.join(gcp_dir, "task.yaml"), "w") as f:
            f.write(task_gcp_content)
        with open(os.path.join(generic_dir, "task.yaml"), "w") as f:
            f.write(task_generic_content)
            
        # Load all tasks
        tasks = load_from_tasks_dir(tmpdir)
        assert len(tasks) == 2
        assert tasks[0]["name"] == "task-gcp"
        assert tasks[1]["name"] == "task-generic"
        
        # Load only generic tasks
        generic_tasks = load_from_tasks_dir(os.path.join(tmpdir, "generic"))
        assert len(generic_tasks) == 1
        assert generic_tasks[0]["name"] == "task-generic"
    finally:
        shutil.rmtree(tmpdir)
