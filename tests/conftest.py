# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Shared fixtures.

pantogloss-translatejson ships as an executable without a .py suffix, so it is
loaded here by path rather than imported. Loading it must not pull in
TensorFlow: the module imports Pantogloss lazily, inside the branch that has
strings left to translate, so the tests stay fast and run without the model.
"""

# importlib.machinery is imported explicitly. Importing importlib.util
# alone does not guarantee the attribute exists; where it appears to,
# some other import has pulled it in, and that difference is invisible
# until the code runs on a machine whose Python has not.
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOURCES = REPO / "distribution" / "src" / "main" / "resources"
BIN = RESOURCES / "bin"
CONF = RESOURCES / "conf"
POLICY = REPO / "pge" / "src" / "main" / "resources" / "policy"
WORKFLOW_POLICY = REPO / "workflow" / "src" / "main" / "resources" / "policy"


def _load_shim():
    path = BIN / "pantogloss-translatejson"
    spec = importlib.util.spec_from_loader(
        "pantogloss_translatejson",
        importlib.machinery.SourceFileLoader("pantogloss_translatejson", str(path)),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["pantogloss_translatejson"] = module
    spec.loader.exec_module(module)
    return module


shim = _load_shim()

Glossary = shim.Glossary
TranslationCache = shim.TranslationCache
collect_strings = shim.collect_strings
load_documents = shim.load_documents
