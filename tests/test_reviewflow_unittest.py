from pathlib import Path
import sys


TESTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_ROOT.parent

if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _reviewflow_unittest_impl import *  # noqa: F403, E402


for _name in (
    "RenderPromptTests",
    "ReviewIntelligenceConfigTests",
    "ChunkHoundConfigTests",
    "CodexConfigTests",
    "LlmPresetConfigTests",
    "AgentRuntimeConfigTests",
    "AgentRuntimePolicyTests",
    "PromptTemplateTests",
    "PromptResourceTests",
    "RuntimeResolutionTests",
    "CanonicalShellOwnershipTests",
):
    globals().pop(_name, None)

del _name
