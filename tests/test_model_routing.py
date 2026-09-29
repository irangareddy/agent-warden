"""Offline checks for per-model streaming and reasoning behavior."""

import os
import sys
import types
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Keep this suite runnable without installing the Flower or OpenAI SDKs.
flwr = types.ModuleType("flwr")
flwr_agentapp = types.ModuleType("flwr.agentapp")
flwr_app = types.ModuleType("flwr.app")
flwr_agentapp.AgentSession = object
flwr_app.Context = object
flwr.agentapp = flwr_agentapp
flwr.app = flwr_app
sys.modules.setdefault("flwr", flwr)
sys.modules.setdefault("flwr.agentapp", flwr_agentapp)
sys.modules.setdefault("flwr.app", flwr_app)

openai = types.ModuleType("openai")
openai.OpenAI = object
sys.modules.setdefault("openai", openai)

from agent.utils import _model_response_mode  # noqa: E402


with patch.dict(os.environ, {}, clear=False):
    os.environ.pop("WARDEN_MODEL_STREAM", None)
    assert _model_response_mode("openai/gpt-5.6-terra") == (True, True)
    assert _model_response_mode("flwrlabs/endeavor-1.0") == (False, False)
    assert _model_response_mode("dedicated/flowerai/Kimi-K2.7-Code-1OUHWL") == (
        False,
        False,
    )
print("PASS default streams with reasoning; Endeavor and dedicated models do neither")

with patch.dict(os.environ, {"WARDEN_MODEL_STREAM": "0"}):
    assert _model_response_mode("openai/gpt-5.6-terra") == (False, True)
print("PASS WARDEN_MODEL_STREAM=0 disables streaming without disabling reasoning")

with patch.dict(os.environ, {"WARDEN_MODEL_STREAM": "1"}):
    assert _model_response_mode("flwrlabs/endeavor-1.0") == (True, False)
    assert _model_response_mode("dedicated/flowerai/MiniMax-M3-OOLI9o") == (
        True,
        False,
    )
print("PASS WARDEN_MODEL_STREAM=1 enables streaming without adding reasoning")
